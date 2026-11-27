"""Read-only Polymarket research. Prices are not independent forecasts."""
import asyncio
import json
import math
import logging
import sqlite3
import re
from contextlib import closing
from datetime import datetime, timezone
import httpx
from fastapi import APIRouter, HTTPException, Query

router = APIRouter(prefix="/api/prediction-markets")
log = logging.getLogger(__name__)
lock = asyncio.Lock()
URL = "https://gamma-api.polymarket.com/markets"
TOPICS = {
    "AI/I": r"artificial intelligence|\bAI\b|semiconductor|chip|data cent[er]+|cloud computing|robotics|quantum|memory|inference",
    "EFM/I": r"nuclear|fusion|uranium|electricity|power grid|energy|oil|natural gas|critical mineral|rare earth|manufacturing|copper",
    "DS/I": r"defen[cs]e|military|satellite|space launch|rocket|cybersecurity|drone|NATO|Taiwan|geopolitic",
    "Human Economy": r"healthcare|employment|housing|consumer|education|transport|automation|medicine",
    "Macro": r"Federal Reserve|interest rate|inflation|recession|GDP|tariff|sanction|trade war|government spending|debt ceiling",
}

def number(value):
    try:
        n = float(value)
        return n if math.isfinite(n) else None
    except (ValueError, TypeError):
        return None

def array(value):
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except ValueError:
            return []
    return value if isinstance(value, list) else []

def normalize(m):
    title = str(m.get("question") or "")
    description = str(m.get("description") or "")
    outcomes, prices = array(m.get("outcomes")), array(m.get("outcomePrices"))
    probabilities = {str(k): n for k, v in zip(outcomes, prices)
                     if (n := number(v)) is not None and 0 <= n <= 1}
    topics = [k for k, pattern in TOPICS.items()
              if re.search(pattern, title + " " + description, re.I)]
    liquidity = number(m.get("liquidityNum", m.get("liquidity")))
    volume = number(m.get("volume24hr"))
    bid, ask = number(m.get("bestBid")), number(m.get("bestAsk"))
    spread = ask - bid if bid is not None and ask is not None and 0 <= bid <= ask <= 1 else None
    quality = "limited" if liquidity is None or liquidity < 10000 or volume is None or volume < 1000 or spread is None or spread > .1 else "higher liquidity"
    return dict(id=str(m["id"]), title=title, description=description, topics=topics,
                probabilities=probabilities, liquidity=liquidity, volume24h=volume, spread=spread,
                quality=quality, end_date=m.get("endDate"), resolution_source=m.get("resolutionSource"),
                slug=m.get("slug"), provider_updated_at=m.get("updatedAt"))

def connect():
    from app.options.api import watchlist_db_path
    db = sqlite3.connect(watchlist_db_path().with_name("rhtc_prediction_markets.sqlite3"), timeout=15)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("CREATE TABLE IF NOT EXISTS scans (stamp TEXT PRIMARY KEY, count INTEGER NOT NULL)")
    db.execute("CREATE TABLE IF NOT EXISTS snapshots (stamp TEXT NOT NULL, id TEXT NOT NULL, payload TEXT NOT NULL, PRIMARY KEY(stamp,id))")
    db.commit()
    return db

async def discover(client):
    # No search terms or portfolio filters are sent to the provider.
    markets = {}
    offset = 0
    while True:
        response = await client.get(URL, params={"active": "true", "closed": "false", "limit": 100, "offset": offset, "order": "id", "ascending": "true"})
        response.raise_for_status()
        page = response.json()
        if not isinstance(page, list):
            raise ValueError("Unexpected market response")
        if not page:
            break
        new_ids = 0
        for m in page:
            mid = str(m["id"])
            if mid not in markets:
                new_ids += 1
            markets[mid] = m
        if not new_ids:
            raise ValueError("Pagination stopped advancing")
        offset += len(page)
        await asyncio.sleep(.1)
    return [normalize(m) for m in markets.values() if m.get("active") is True and m.get("closed") is False]

async def refresh():
    async with lock:
        async with httpx.AsyncClient(timeout=30) as client:
            rows = await discover(client)
        if not rows:
            raise ValueError("Empty scan; previous snapshot retained")
        stamp = datetime.now(timezone.utc).isoformat()
        with closing(connect()) as db, db:
            db.execute("INSERT INTO scans VALUES (?,?)", (stamp, len(rows)))
            db.executemany("INSERT INTO snapshots VALUES (?,?,?)",
                           [(stamp, m["id"], json.dumps(m)) for m in rows])
        return {"as_of": stamp, "count": len(rows)}

async def scheduler():
    while True:
        try:
            with closing(connect()) as db:
                latest = db.execute("SELECT MAX(stamp) FROM scans").fetchone()[0]
            if not latest or (datetime.now(timezone.utc)-datetime.fromisoformat(latest)).total_seconds() >= 21600:
                await refresh()
        except Exception:
            log.exception("Prediction market scan failed; retaining prior complete scan")
        await asyncio.sleep(900)

def latest():
    with closing(connect()) as db:
        scan = db.execute("SELECT stamp,count FROM scans ORDER BY stamp DESC LIMIT 1").fetchone()
        if not scan:
            return None, []
        return dict(scan), [json.loads(r[0]) for r in db.execute("SELECT payload FROM snapshots WHERE stamp=?", (scan["stamp"],))]

@router.get("")
def markets(topic: str = "All", offset: int = Query(0, ge=0), limit: int = Query(100, ge=1, le=500)):
    scan, rows = latest()
    if topic != "All":
        rows = [r for r in rows if topic in r["topics"] or (topic == "Unclassified" and not r["topics"])]
    rows.sort(key=lambda r: (bool(r["topics"]), r["liquidity"] or 0), reverse=True)
    return {"scan": scan, "count": len(rows), "markets": rows[offset:offset+limit],
            "caution": "Market prices are complementary evidence only; independently verify fundamentals and resolution rules."}

@router.post("/refresh")
async def refresh_markets():
    if lock.locked():
        raise HTTPException(409, "Scan already running")
    try:
        return await refresh()
    except Exception:
        log.exception("Manual prediction market scan failed")
        raise HTTPException(502, "Scan failed; previous complete snapshot retained")
