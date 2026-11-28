"""Bounded read-only shadow quote refresh; no snapshot publication or AI calls."""
import asyncio
import json
import logging
from contextlib import closing
from datetime import timedelta
import httpx
from app.options import kalshi_ingestion as ki, kalshi_provider as kp

log=logging.getLogger(__name__)
lock=asyncio.Lock()
MAX_CONTRACTS=200
CHUNK=50

def connect():
    db=ki.connect()
    db.executescript("""
        CREATE TABLE IF NOT EXISTS quote_observations(id TEXT NOT NULL,observed_at TEXT NOT NULL,payload TEXT NOT NULL,PRIMARY KEY(id,observed_at));
        CREATE INDEX IF NOT EXISTS quote_observed_at ON quote_observations(observed_at);
        CREATE TABLE IF NOT EXISTS quote_current(id TEXT PRIMARY KEY,observed_at TEXT NOT NULL,payload TEXT NOT NULL);
    """)
    return db

def candidates():
    # Use the shared fingerprint-matched research cache. Limit work to the
    # latest fully indexed snapshot and rotate within priority classes.
    from app.options import prediction_markets as pm
    from app.options.api import watchlist_db_path,read_watchlist
    held={str(w["symbol"]).upper() for w in read_watchlist() if (pm.number(w.get("quantity")) or 0)>0}
    with closing(connect()) as db:
        scan=db.execute("SELECT stamp,count FROM scans ORDER BY stamp DESC LIMIT 1").fetchone()
        if not scan:
            return []
        count=db.execute("SELECT COUNT(*) FROM market_catalog WHERE stamp=?",(scan["stamp"],)).fetchone()[0]
        if count!=scan["count"]:
            return []
        with closing(pm.connect()):
            pass
        db.execute("ATTACH DATABASE ? AS researchdb",(str(watchlist_db_path().with_name("rhtc_prediction_markets.sqlite3")),))
        db.execute("CREATE TEMP TABLE held(symbol TEXT PRIMARY KEY)")
        db.executemany("INSERT INTO held VALUES (?)",[(x,) for x in held])
        # Prioritize direct holdings and reviewed strategic relevance, with
        # oldest observed first within each priority tier.
        sql="""SELECT c.id FROM market_catalog c
          LEFT JOIN researchdb.market_research r ON r.id=c.id AND r.fingerprint=c.fingerprint
          LEFT JOIN quote_current q ON q.id=c.id
          WHERE c.stamp=? AND (q.observed_at IS NULL OR q.observed_at<?)
          ORDER BY
          (EXISTS(SELECT 1 FROM json_each(c.tickers) t JOIN held h ON h.symbol=t.value)
           OR EXISTS(SELECT 1 FROM json_each(r.payload,'$.tickers') t JOIN held h ON h.symbol=t.value)) DESC,
          COALESCE(CAST(json_extract(r.payload,'$.relevance') AS REAL),0) DESC,
          c.quality DESC, COALESCE(q.observed_at,'') ASC,c.liquidity DESC,c.id
          LIMIT ?"""
        return [r[0] for r in db.execute(sql,(scan["stamp"],(ki.now()-timedelta(minutes=15)).isoformat(),MAX_CONTRACTS))]

def persist(requested,markets):
    stamp=ki.now().isoformat()
    expected=set(requested)
    seen=set()
    rows=[]
    for market in markets:
        row=kp.normalize(market)
        mid=row["id"]
        if mid not in expected or mid in seen:
            raise ValueError("Unexpected or duplicate quote market")
        seen.add(mid)
        state=market.get("status")
        if not isinstance(state,str) or not state:
            raise ValueError("Missing quote lifecycle state")
        key,_,_=ki.compact(row)
        # Keep exact contract metadata identity with the quote. Do not
        # imply that a changed contract is comparable with its old history.
        data={k:row[k] for k in ("probabilities","probability_method","last_price","spread","volume24h","open_interest","liquidity","quality","provider_updated_at")}
        data.update(metadata_key=key,status=state,observed_at=stamp)
        if state not in ("active","open"):
            data["probabilities"]={}
            data["quality"]="limited"
        rows.append((mid,stamp,json.dumps(data,allow_nan=False)))
    with closing(connect()) as db,db:
        db.execute("BEGIN IMMEDIATE")
        db.executemany("INSERT INTO quote_observations VALUES (?,?,?)",rows)
        db.executemany("""INSERT INTO quote_current VALUES (?,?,?) ON CONFLICT(id)
            DO UPDATE SET observed_at=excluded.observed_at,payload=excluded.payload
            WHERE excluded.observed_at>quote_current.observed_at""",rows)
        # Missing tickers are not given fabricated observations.
    return len(rows)

async def refresh():
    async with lock:
        ids=await asyncio.to_thread(candidates)
        if not ids:
            return 0
        saved=0
        async with httpx.AsyncClient(timeout=30) as client:
            for start in range(0,len(ids),CHUNK):
                if await asyncio.to_thread(ki.headroom)<.15:
                    break
                chunk=ids[start:start+CHUNK]
                tickers=[mid.removeprefix("kalshi:") for mid in chunk]
                markets,cursor=await kp.fetch_page(client,limit=CHUNK,tickers=tickers)
                if cursor:
                    raise ValueError("Unexpected pagination for bounded quote request")
                saved+=await asyncio.to_thread(persist,chunk,markets)
                await asyncio.sleep(.2)
        log.warning("Kalshi shadow quote refresh: %d/%d requested markets saved",saved,len(ids))
        return saved

async def scheduler():
    while True:
        try:
            await refresh()
        except Exception:
            log.exception("Kalshi shadow quote refresh failed; prior observations retained")
        await asyncio.sleep(900)
