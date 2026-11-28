"""Shadow metadata synchronization. Never publishes prices or replaces full scans."""
import asyncio
import json
import logging
from contextlib import closing
from datetime import datetime, timezone
import httpx
from app.options import kalshi_ingestion as ki, kalshi_provider as kp

log = logging.getLogger(__name__)
lock = asyncio.Lock()


def connect():
    db=ki.connect()
    db.executescript("""
      CREATE TABLE IF NOT EXISTS metadata_watermark(id INTEGER PRIMARY KEY CHECK(id=1), upper_ts INTEGER NOT NULL);
      CREATE TABLE IF NOT EXISTS metadata_checkpoint(id INTEGER PRIMARY KEY CHECK(id=1), lower_ts INTEGER NOT NULL, upper_ts INTEGER NOT NULL, cursor TEXT, pages INTEGER NOT NULL, exhausted INTEGER NOT NULL);
      CREATE TABLE IF NOT EXISTS metadata_cursors(upper_ts INTEGER NOT NULL,cursor TEXT NOT NULL,PRIMARY KEY(upper_ts,cursor));
      CREATE TABLE IF NOT EXISTS metadata_stage(upper_ts INTEGER NOT NULL,id TEXT NOT NULL,provider_ts TEXT NOT NULL,metadata_key TEXT NOT NULL,status TEXT NOT NULL,PRIMARY KEY(upper_ts,id));
      CREATE TABLE IF NOT EXISTS metadata_current(id TEXT PRIMARY KEY,provider_ts TEXT NOT NULL,metadata_key TEXT NOT NULL,status TEXT NOT NULL);
    """)
    return db


def begin():
    with closing(connect()) as db,db:
        db.execute("BEGIN IMMEDIATE")
        cp=db.execute("SELECT * FROM metadata_checkpoint WHERE id=1").fetchone()
        if cp:
            return dict(cp)
        latest=db.execute("SELECT MAX(stamp) FROM scans").fetchone()[0]
        if not latest:
            return None
        watermark=db.execute("SELECT upper_ts FROM metadata_watermark WHERE id=1").fetchone()
        baseline=watermark[0] if watermark else int(datetime.fromisoformat(latest).timestamp())
        # Overlap to tolerate boundary ties; do not chase a moving upper bound.
        upper=int(datetime.now(timezone.utc).timestamp())-120
        if upper<=baseline:
            return None
        lower=max(0,baseline-300)
        db.execute("INSERT INTO metadata_checkpoint VALUES(1,?,?,NULL,0,0)",(lower,upper))
        return dict(db.execute("SELECT * FROM metadata_checkpoint WHERE id=1").fetchone())


def owner(db,cp):
    row=db.execute("SELECT * FROM metadata_checkpoint WHERE id=1").fetchone()
    if row is None or dict(row)!=cp:
        raise ValueError("Metadata checkpoint changed")


def persist(cp,page,cursor):
    rows=[]
    for m in page:
        if m.get("market_type")!="binary":
            continue
        row=kp.normalize(m)
        ts=datetime.fromisoformat(str(m.get("updated_time")).replace("Z","+00:00"))
        if ts.tzinfo is None or not cp["lower_ts"]<=ts.timestamp()<cp["upper_ts"]+1:
            raise ValueError("Metadata timestamp outside requested window")
        state=m.get("status")
        if not isinstance(state,str) or not state:
            raise ValueError("Missing market lifecycle state")
        key,metadata,_=ki.compact(row)
        rows.append((row["id"],ts.astimezone(timezone.utc).isoformat(timespec="microseconds"),key,metadata,state))
    with closing(connect()) as db,db:
        db.execute("BEGIN IMMEDIATE")
        owner(db,cp)
        if cp["exhausted"]:
            raise ValueError("Metadata checkpoint exhausted")
        if cursor:
            if not page or cursor==cp["cursor"] or db.execute("SELECT 1 FROM metadata_cursors WHERE upper_ts=? AND cursor=?",(cp["upper_ts"],cursor)).fetchone():
                raise ValueError("Metadata cursor stopped advancing")
            db.execute("INSERT INTO metadata_cursors VALUES (?,?)",(cp["upper_ts"],cursor))
        for mid,ts,key,meta,state in rows:
            db.execute("INSERT OR IGNORE INTO market_metadata VALUES (?,?)",(key,meta))
            db.execute("""INSERT INTO metadata_stage VALUES (?,?,?,?,?)
                ON CONFLICT(upper_ts,id) DO UPDATE SET provider_ts=excluded.provider_ts,metadata_key=excluded.metadata_key,status=excluded.status
                WHERE excluded.provider_ts>=metadata_stage.provider_ts""",(cp["upper_ts"],mid,ts,key,state))
        db.execute("UPDATE metadata_checkpoint SET cursor=?,pages=pages+1,exhausted=? WHERE id=1",(cursor,int(not cursor)))
        return dict(db.execute("SELECT * FROM metadata_checkpoint WHERE id=1").fetchone())


def finish(cp):
    with closing(connect()) as db,db:
        db.execute("BEGIN IMMEDIATE")
        owner(db,cp)
        if not cp["exhausted"]:
            raise ValueError("Cannot publish incomplete metadata window")
        count=db.execute("SELECT COUNT(*) FROM metadata_stage WHERE upper_ts=?",(cp["upper_ts"],)).fetchone()[0]
        db.execute("""INSERT INTO metadata_current SELECT id,provider_ts,metadata_key,status FROM metadata_stage WHERE upper_ts=?
            ON CONFLICT(id) DO UPDATE SET provider_ts=excluded.provider_ts,metadata_key=excluded.metadata_key,status=excluded.status
            WHERE excluded.provider_ts>=metadata_current.provider_ts""",(cp["upper_ts"],))
        db.execute("INSERT OR REPLACE INTO metadata_watermark VALUES(1,?)",(cp["upper_ts"],))
        db.execute("DELETE FROM metadata_stage WHERE upper_ts=?",(cp["upper_ts"],))
        db.execute("DELETE FROM metadata_cursors WHERE upper_ts=?",(cp["upper_ts"],))
        db.execute("DELETE FROM metadata_checkpoint WHERE id=1")
        return count


async def refresh():
    async with lock:
        cp=await asyncio.to_thread(begin)
        if cp is None:
            return None
        async with httpx.AsyncClient(timeout=30) as client:
            while not cp["exhausted"]:
                if await asyncio.to_thread(ki.headroom)<.15:
                    raise ValueError("Metadata synchronization paused for storage headroom")
                page,cursor=await kp.fetch_page(client,cp["cursor"],limit=1000,updated_window=(cp["lower_ts"],cp["upper_ts"]))
                cp=await asyncio.to_thread(persist,cp,page,cursor)
                await asyncio.sleep(.1)
        count=await asyncio.to_thread(finish,cp)
        log.warning("Kalshi shadow metadata sync completed: %d changed contracts; watermark %d",count,cp["upper_ts"])
        return count


async def scheduler():
    while True:
        try:
            await refresh()
        except Exception:
            log.exception("Kalshi shadow metadata synchronization failed; retained watermark")
        await asyncio.sleep(900)
