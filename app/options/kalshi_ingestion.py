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
    """)
    return db


def begin():
    with closing(connect()) as db, db:
        db.execute("BEGIN IMMEDIATE")
        db.execute("INSERT OR IGNORE INTO checkpoint VALUES(1,?,NULL,0,0)", (now().isoformat(),))
        return dict(db.execute("SELECT * FROM checkpoint WHERE id=1").fetchone())


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
            db.execute("DELETE FROM snapshots WHERE stamp IN (SELECT stamp FROM scans WHERE stamp<? AND stamp<>?)",
                       (cutoff, cp["stamp"]))
            db.execute("DELETE FROM scans WHERE stamp<? AND stamp<>?", (cutoff, cp["stamp"]))
    if not count:
        raise ValueError("Empty Kalshi scan; prior completed scan retained")
    return count


def latest():
    with closing(connect()) as db:
        db.execute("BEGIN")
        scan = db.execute("SELECT * FROM scans ORDER BY stamp DESC LIMIT 1").fetchone()
        if not scan:
            return None, []
        rows = [json.loads(r[0]) for r in db.execute("SELECT payload FROM snapshots WHERE stamp=?", (scan["stamp"],))]
        return dict(scan), rows


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
            async with httpx.AsyncClient(timeout=30) as client:
                while not cp["exhausted"]:
                    if cp["pages"] % 20 == 0 and headroom() < .15:
                        raise ValueError("Storage above 85% utilization; Kalshi scan paused")
                    page, cursor = await kalshi_provider.fetch_page(client, cp["cursor"])
                    cp = await asyncio.to_thread(persist, cp, page, cursor)
                    await asyncio.to_thread(status, "running", pages=cp["pages"])
                    await asyncio.sleep(.1)
            count = await asyncio.to_thread(finish, cp)
            await asyncio.to_thread(status, "completed", pages=cp["pages"], active=count)
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
