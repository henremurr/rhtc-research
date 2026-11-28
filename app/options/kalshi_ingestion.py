"""Durable independent Kalshi ingestion; only completed scans are published."""
import asyncio
import json
import logging
import sqlite3
import shutil
from contextlib import closing
from datetime import datetime, timezone, timedelta
import httpx
from app.options import kalshi_provider

log = logging.getLogger(__name__)
lock = asyncio.Lock()


def now():
    return datetime.now(timezone.utc)


def connect():
    from app.options.api import watchlist_db_path
    db = sqlite3.connect(watchlist_db_path().with_name("rhtc_kalshi.sqlite3"), timeout=15)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA journal_mode=WAL")
    db.executescript("""
        CREATE TABLE IF NOT EXISTS scans(stamp TEXT PRIMARY KEY, count INTEGER NOT NULL);
        CREATE TABLE IF NOT EXISTS snapshots(stamp TEXT NOT NULL,id TEXT NOT NULL,payload TEXT NOT NULL,PRIMARY KEY(stamp,id));
        CREATE INDEX IF NOT EXISTS snapshot_history ON snapshots(id,stamp);
        CREATE TABLE IF NOT EXISTS checkpoint(id INTEGER PRIMARY KEY CHECK(id=1),stamp TEXT NOT NULL,cursor TEXT,pages INTEGER NOT NULL,exhausted INTEGER NOT NULL);
        CREATE TABLE IF NOT EXISTS cursors(stamp TEXT NOT NULL,cursor TEXT NOT NULL,PRIMARY KEY(stamp,cursor));
        CREATE TABLE IF NOT EXISTS status(id INTEGER PRIMARY KEY CHECK(id=1),payload TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS scan_settings(stamp TEXT PRIMARY KEY,page_size INTEGER NOT NULL);
        CREATE TABLE IF NOT EXISTS market_catalog(stamp TEXT NOT NULL,id TEXT NOT NULL,fingerprint TEXT NOT NULL,topics TEXT NOT NULL,tickers TEXT NOT NULL,search_text TEXT NOT NULL,liquidity REAL NOT NULL,quality INTEGER NOT NULL,PRIMARY KEY(stamp,id));
        CREATE INDEX IF NOT EXISTS market_catalog_order ON market_catalog(stamp,quality DESC,liquidity DESC,id);
        CREATE TABLE IF NOT EXISTS market_catalog_state(stamp TEXT PRIMARY KEY,last_id TEXT NOT NULL,complete INTEGER NOT NULL DEFAULT 0);
    """)
    return db


def begin():
    with closing(connect()) as db, db:
        db.execute("BEGIN IMMEDIATE")
        existing=db.execute("SELECT * FROM checkpoint WHERE id=1").fetchone()
        if existing:
            # Legacy checkpoints were created with 100-item pages.
            db.execute("INSERT OR IGNORE INTO scan_settings VALUES(?,100)",(existing["stamp"],))
        else:
            stamp=now().isoformat()
            db.execute("INSERT INTO checkpoint VALUES(1,?,NULL,0,0)",(stamp,))
            db.execute("INSERT INTO scan_settings VALUES(?,1000)",(stamp,))
        return dict(db.execute("SELECT * FROM checkpoint WHERE id=1").fetchone())


def page_size(cp):
    with closing(connect()) as db:
        row=db.execute("SELECT page_size FROM scan_settings WHERE stamp=?",(cp["stamp"],)).fetchone()
        return row[0] if row else 100


def status(state, **details):
    with closing(connect()) as db, db:
        db.execute("INSERT OR REPLACE INTO status VALUES(1,?)",
                   (json.dumps(dict(state=state, updated_at=now().isoformat(), **details)),))


def read_status():
    with closing(connect()) as db:
        row = db.execute("SELECT payload FROM status WHERE id=1").fetchone()
        return json.loads(row[0]) if row else {"state": "not started"}


def assert_owner(db, cp):
    current = db.execute("SELECT * FROM checkpoint WHERE id=1").fetchone()
    if current is None or dict(current) != cp:
        raise ValueError("Kalshi checkpoint changed")


def persist(cp, page, cursor):
    rows = []
    for market in page:
        if market.get("market_type") != "binary" or market.get("status") not in ("active", "open"):
            continue
        row = kalshi_provider.normalize(market)
        row["observed_at"] = now().isoformat()
        rows.append(row)
    with closing(connect()) as db, db:
        db.execute("BEGIN IMMEDIATE")
        assert_owner(db, cp)
        if cp["exhausted"]:
            raise ValueError("Kalshi scan already exhausted")
        if cursor:
            if not page or cursor == cp["cursor"] or db.execute(
                "SELECT 1 FROM cursors WHERE stamp=? AND cursor=?", (cp["stamp"], cursor)
            ).fetchone():
                raise ValueError("Kalshi cursor stopped advancing")
            db.execute("INSERT INTO cursors VALUES(?,?)", (cp["stamp"], cursor))
        db.executemany("INSERT OR REPLACE INTO snapshots VALUES(?,?,?)",
                       [(cp["stamp"], r["id"], json.dumps(r, allow_nan=False)) for r in rows])
        from app.options import prediction_markets as pm
        pm.classify_kalshi(rows)
        db.executemany("INSERT OR REPLACE INTO market_catalog VALUES (?,?,?,?,?,?,?,?)", [pm.catalog_record(cp["stamp"],r) for r in rows])
        db.execute("UPDATE checkpoint SET cursor=?,pages=pages+1,exhausted=? WHERE id=1",
                   (cursor, int(not cursor)))
        return dict(db.execute("SELECT * FROM checkpoint WHERE id=1").fetchone())


def finish(cp):
    with closing(connect()) as db, db:
        db.execute("BEGIN IMMEDIATE")
        assert_owner(db, cp)
        if not cp["exhausted"]:
            raise ValueError("Cannot publish incomplete Kalshi scan")
        count = db.execute("SELECT COUNT(*) FROM snapshots WHERE stamp=?", (cp["stamp"],)).fetchone()[0]
        if not count:
            # Discard an exhausted empty attempt so the next cycle can retry.
            db.execute("DELETE FROM cursors WHERE stamp=?", (cp["stamp"],))
            db.execute("DELETE FROM checkpoint WHERE id=1")
        else:
            db.execute("INSERT INTO scans VALUES(?,?)", (cp["stamp"], count))
            db.execute("DELETE FROM cursors WHERE stamp=?", (cp["stamp"],))
            db.execute("DELETE FROM checkpoint WHERE id=1")
            cutoff = (now() - timedelta(days=35)).isoformat()
            db.execute("DELETE FROM market_catalog WHERE stamp IN (SELECT stamp FROM scans WHERE stamp<? AND stamp<>?)",(cutoff,cp["stamp"]))
            db.execute("DELETE FROM market_catalog_state WHERE stamp IN (SELECT stamp FROM scans WHERE stamp<? AND stamp<>?)",(cutoff,cp["stamp"]))
            db.execute("DELETE FROM snapshots WHERE stamp IN (SELECT stamp FROM scans WHERE stamp<? AND stamp<>?)",
                       (cutoff, cp["stamp"]))
            db.execute("DELETE FROM scans WHERE stamp<? AND stamp<>?", (cutoff, cp["stamp"]))
        db.execute("DELETE FROM scan_settings WHERE stamp=?",(cp["stamp"],))
    if not count:
        raise ValueError("Empty Kalshi scan; prior completed scan retained")
    return count


def backfill_latest_catalog(batch_size=500):
    """Index a bounded batch from the latest completed scan; never alter snapshots."""
    from app.options import prediction_markets as pm
    with closing(connect()) as db, db:
        db.execute("BEGIN IMMEDIATE")
        scan=db.execute("SELECT stamp,count FROM scans ORDER BY stamp DESC LIMIT 1").fetchone()
        if not scan:
            return True
        stamp=scan["stamp"]
        state=db.execute("SELECT last_id,complete FROM market_catalog_state WHERE stamp=?",(stamp,)).fetchone()
        if state and state["complete"]:
            return True
        last=state["last_id"] if state else ""
        records=db.execute("SELECT id,payload FROM snapshots WHERE stamp=? AND id>? ORDER BY id LIMIT ?",(stamp,last,batch_size)).fetchall()
        if not records:
            count=db.execute("SELECT COUNT(*) FROM market_catalog WHERE stamp=?",(stamp,)).fetchone()[0]
            if count!=scan["count"]:
                raise ValueError("Kalshi catalog count mismatch")
            db.execute("INSERT OR REPLACE INTO market_catalog_state VALUES (?,?,1)",(stamp,last))
            return True
        rows=[json.loads(record["payload"]) for record in records]
        pm.classify_kalshi(rows)
        db.executemany("INSERT OR IGNORE INTO market_catalog VALUES (?,?,?,?,?,?,?,?)",[pm.catalog_record(stamp,r) for r in rows])
        db.execute("INSERT OR REPLACE INTO market_catalog_state VALUES (?,?,0)",(stamp,records[-1]["id"]))
        return False


def latest(search=None):
    with closing(connect()) as db:
        db.execute("BEGIN")
        scan = db.execute("SELECT * FROM scans ORDER BY stamp DESC LIMIT 1").fetchone()
        if not scan:
            return None, []
        if search is None:
            records = db.execute("SELECT payload FROM snapshots WHERE stamp=?", (scan["stamp"],))
        else:
            def matches(title, description):
                return int(bool(search.search(title or "") or search.search(description or "")))
            db.create_function("kalshi_matches", 2, matches, deterministic=True)
            records = db.execute(
                "SELECT payload FROM snapshots WHERE stamp=? AND "
                "kalshi_matches(json_extract(payload,'$.title'),json_extract(payload,'$.description'))",
                (scan["stamp"],))
        rows = [json.loads(r[0]) for r in records]
        return dict(scan), rows


def add_history(scan, rows):
    if not scan:
        return rows
    stamp = datetime.fromisoformat(scan["stamp"])
    ids = list(dict.fromkeys(row["id"] for row in rows))
    with closing(connect()) as db:
        for days in (1, 7, 30):
            target = stamp - timedelta(days=days)
            prior = db.execute("SELECT MAX(stamp) FROM scans WHERE stamp<=?",
                               (target.isoformat(),)).fetchone()[0]
            old = {}
            if prior and target - datetime.fromisoformat(prior) <= timedelta(hours=12):
                for start in range(0, len(ids), 500):
                    chunk = ids[start:start+500]
                    sql = ("SELECT id,json_extract(payload,'$.probabilities') FROM snapshots "
                           "WHERE stamp=? AND id IN (" + ",".join("?" for _ in chunk) + ")")
                    old.update((r[0], json.loads(r[1] or "{}"))
                               for r in db.execute(sql, (prior, *chunk)))
            for row in rows:
                previous = old.get(row["id"], {})
                row.setdefault("changes_pp", {})[str(days)] = {
                    label: round((value - previous[label]) * 100, 2)
                    for label, value in row["probabilities"].items() if label in previous
                }
    return rows

def due():
    with closing(connect()) as db:
        if db.execute("SELECT 1 FROM checkpoint").fetchone():
            return True
        stamp = db.execute("SELECT MAX(stamp) FROM scans").fetchone()[0]
        return not stamp or (now() - datetime.fromisoformat(stamp)).total_seconds() >= 21600


def headroom():
    from app.options.api import watchlist_db_path
    disk = shutil.disk_usage(watchlist_db_path().parent)
    return disk.free / disk.total if disk.total else 0


async def refresh():
    async with lock:
        cp = await asyncio.to_thread(begin)
        try:
            await asyncio.to_thread(status, "running", pages=cp["pages"])
            log.warning("Kalshi discovery started or resumed: %d pages", cp["pages"])
            limit=await asyncio.to_thread(page_size,cp)
            async with httpx.AsyncClient(timeout=30) as client:
                while not cp["exhausted"]:
                    if cp["pages"] % 20 == 0 and headroom() < .15:
                        raise ValueError("Storage above 85% utilization; Kalshi scan paused")
                    page, cursor = await kalshi_provider.fetch_page(client, cp["cursor"], limit=limit)
                    cp = await asyncio.to_thread(persist, cp, page, cursor)
                    await asyncio.to_thread(status, "running", pages=cp["pages"])
                    if cp["pages"] % 20 == 0:
                        log.warning("Kalshi discovery progress: %d pages", cp["pages"])
                    await asyncio.sleep(.1)
            count = await asyncio.to_thread(finish, cp)
            await asyncio.to_thread(status, "completed", pages=cp["pages"], active=count)
            log.warning("Kalshi discovery completed: %d active markets, %d pages", count, cp["pages"])
            from app.options.prediction_health import request_refresh
            request_refresh()
            return {"as_of": cp["stamp"], "count": count}
        except asyncio.CancelledError:
            await asyncio.to_thread(status, "interrupted", pages=cp["pages"])
            raise
        except Exception as exc:
            reason = ("Provider HTTP " + str(exc.response.status_code)
                      if isinstance(exc, httpx.HTTPStatusError) else
                      str(exc)[:200] if isinstance(exc, ValueError) else type(exc).__name__)
            await asyncio.to_thread(status, "failed", error=reason, pages=cp["pages"])
            raise


async def scheduler():
    while True:
        try:
            if await asyncio.to_thread(due):
                await refresh()
        except Exception:
            log.exception("Kalshi scan failed; retaining prior complete snapshot")
        await asyncio.sleep(900)
