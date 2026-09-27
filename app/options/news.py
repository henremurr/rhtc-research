from __future__ import annotations

import asyncio
import logging
import os
import sqlite3
from contextlib import closing
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

import httpx
from fastapi import APIRouter, HTTPException, Query

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/news", tags=["news"])
SEARCH_URL = "https://api.perplexity.ai/search"
PACIFIC = ZoneInfo("America/Los_Angeles")
SCAN_LOCK = asyncio.Lock()
MAX_ARTICLES_PER_SCAN = 25
MAX_RESULTS_PER_QUERY = 20

SEARCH_QUERIES = [
    "AI compute infrastructure, semiconductors, GPUs, memory, networking, hyperscalers and data center investment latest news",
    "electric power, grid, generation, nuclear energy, uranium, natural gas, LNG, critical minerals and infrastructure latest news",
    "US defense, Pentagon, military procurement, missiles, munitions, drones, electronic warfare and security latest news",
    "space industry, launch, satellites, Space Force, NASA, commercial spaceflight and national security space latest news",
    "new reports and analysis from CSIS, Hudson Institute, FDD, Heritage Foundation and other think tanks on AI, energy, defense and space",
]

PEAK_TERMS = {
    "AI/I": ("artificial intelligence", " ai ", "semiconductor", "chip", "gpu", "compute", "hyperscaler", "data center", "datacenter", "memory", "cloud", "networking"),
    "EFM/I": ("electricity", "power", "grid", "nuclear", "uranium", "natural gas", "lng", "fuel", "critical mineral", "mining", "pipeline", "energy", "oil", "electric utility"),
    "DS/I": ("defense", "military", "pentagon", "missile", "munitions", "drone", "electronic warfare", "air force", "navy", "army", "satellite", "space force", "spacecraft", "launch", "orbital", "national security", "rocket"),
}


def db_path() -> Path:
    data_dir = Path(os.getenv("RHTC_DATA_DIR", str(Path(__file__).parent.parent.parent / "data")))
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir / "rhtc_symbols.sqlite3"


def connect_db() -> sqlite3.Connection:
    connection = sqlite3.connect(db_path(), timeout=15)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute(
        """CREATE TABLE IF NOT EXISTS news_items (
            url TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            source TEXT NOT NULL,
            published_at TEXT NOT NULL DEFAULT '',
            snippet TEXT NOT NULL DEFAULT '',
            peak TEXT NOT NULL DEFAULT 'Other',
            first_seen_at TEXT NOT NULL,
            last_seen_at TEXT NOT NULL
        )"""
    )
    connection.execute("CREATE TABLE IF NOT EXISTS news_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
    connection.commit()
    return connection


def now_pacific() -> datetime:
    return datetime.now(PACIFIC).replace(microsecond=0)


def classify_peak(title: str, snippet: str) -> str:
    text = f" {title} {snippet} ".lower()
    matches = [peak for peak, terms in PEAK_TERMS.items() if any(term in text for term in terms)]
    if len(matches) > 1:
        return "Cross-Peak"
    return matches[0] if matches else "Other"


def clean_result(item: dict[str, Any], seen_at: str) -> dict[str, str] | None:
    title = str(item.get("title") or "").strip()[:500]
    url = str(item.get("url") or "").strip()
    parsed = urlparse(url)
    if not title or parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return None
    source = (parsed.hostname or "").removeprefix("www.")[:200]
    snippet = str(item.get("snippet") or "").strip()[:3000]
    return {
        "url": url[:2000],
        "title": title,
        "source": source,
        "published_at": str(item.get("date") or item.get("last_updated") or "")[:40],
        "snippet": snippet,
        "peak": classify_peak(title, snippet),
        "seen_at": seen_at,
    }


def latest_scan_at(connection: sqlite3.Connection) -> str | None:
    row = connection.execute("SELECT value FROM news_meta WHERE key='last_scan_at'").fetchone()
    return row["value"] if row else None


async def scan_news(*, scheduled: bool = False) -> dict[str, Any]:
    async with SCAN_LOCK:
        api_key = os.getenv("PERPLEXITY_API_KEY")
        if not api_key:
            raise HTTPException(503, "News search is not configured. Add PERPLEXITY_API_KEY to the Railway service variables.")

        with closing(connect_db()) as connection:
            previous = latest_scan_at(connection)
        if previous:
            try:
                last = datetime.fromisoformat(previous)
                if last.tzinfo is None:
                    last = last.replace(tzinfo=PACIFIC)
                if not scheduled and (now_pacific() - last.astimezone(PACIFIC)) < timedelta(minutes=10):
                    return {"status": "recent", "last_scan_at": previous, "added": 0}
            except ValueError:
                pass

        payload = {
            "query": SEARCH_QUERIES,
            "max_results": MAX_RESULTS_PER_QUERY,
            "search_type": "fast",
            "search_recency_filter": "day",
            "search_language_filter": ["en"],
            "search_context_size": "low",
        }
        try:
            async with httpx.AsyncClient(timeout=45.0) as client:
                response = await client.post(
                    SEARCH_URL,
                    headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                    json=payload,
                )
                response.raise_for_status()
                data = response.json()
        except httpx.TimeoutException as exc:
            logger.warning("RHTC news search timed out: %s", exc)
            raise HTTPException(502, "News search timed out. Try again later.") from exc
        except httpx.HTTPStatusError as exc:
            logger.warning("RHTC news provider returned HTTP %s", exc.response.status_code)
            raise HTTPException(502, "The news provider returned an error. Check the API key and try again later.") from exc
        except (httpx.HTTPError, ValueError) as exc:
            logger.warning("RHTC news search failed: %s", exc)
            raise HTTPException(502, "News search could not be completed. Try again later.") from exc

        if not isinstance(data, dict) or not isinstance(data.get("results", []), list):
            logger.warning("RHTC news provider returned an unexpected response shape")
            raise HTTPException(502, "The news provider returned an unexpected response. Try again later.")

        seen_at = now_pacific().isoformat()
        raw_results = data.get("results") or []
        clean_items: dict[str, dict[str, str]] = {}
        for raw in raw_results:
            if isinstance(raw, dict):
                cleaned = clean_result(raw, seen_at)
                if cleaned:
                    clean_items[cleaned["url"]] = cleaned
                    if len(clean_items) >= MAX_ARTICLES_PER_SCAN:
                        break

        with closing(connect_db()) as connection:
            connection.executemany(
                """INSERT INTO news_items(url,title,source,published_at,snippet,peak,first_seen_at,last_seen_at)
                   VALUES(:url,:title,:source,:published_at,:snippet,:peak,:seen_at,:seen_at)
                   ON CONFLICT(url) DO UPDATE SET title=excluded.title, source=excluded.source,
                     published_at=excluded.published_at, snippet=excluded.snippet, peak=excluded.peak,
                     last_seen_at=excluded.last_seen_at""",
                list(clean_items.values()),
            )
            connection.execute("DELETE FROM news_items WHERE first_seen_at < ?", ((now_pacific() - timedelta(days=90)).isoformat(),))
            connection.execute("INSERT OR REPLACE INTO news_meta(key,value) VALUES('last_scan_at',?)", (seen_at,))
            connection.execute("INSERT OR REPLACE INTO news_meta(key,value) VALUES('last_scan_count',?)", (str(len(clean_items)),))
            connection.commit()
            total = connection.execute("SELECT COUNT(*) AS n FROM news_items").fetchone()["n"]

        return {"status": "complete", "last_scan_at": seen_at, "added": len(clean_items), "total": total}


@router.get("")
async def get_news(
    peak: str | None = Query(default=None, max_length=20),
    q: str | None = Query(default=None, max_length=120),
    days: int = Query(default=14, ge=1, le=90),
):
    cutoff = (now_pacific() - timedelta(days=days)).isoformat()
    query = "SELECT url,title,source,published_at,snippet,peak,first_seen_at FROM news_items WHERE first_seen_at >= ?"
    params: list[Any] = [cutoff]
    if peak and peak not in {"All", "All Peaks"}:
        query += " AND peak = ?"
        params.append(peak)
    if q and q.strip():
        query += " AND (title LIKE ? OR snippet LIKE ? OR source LIKE ?)"
        term = f"%{q.strip()}%"
        params.extend([term, term, term])
    query += " ORDER BY COALESCE(NULLIF(published_at,''), first_seen_at) DESC, first_seen_at DESC LIMIT 150"
    with closing(connect_db()) as connection:
        rows = [dict(row) for row in connection.execute(query, params)]
        meta = {row["key"]: row["value"] for row in connection.execute("SELECT key,value FROM news_meta")}
    return {
        "items": rows,
        "total": len(rows),
        "last_scan_at": meta.get("last_scan_at"),
        "last_scan_count": int(meta.get("last_scan_count", "0")),
        "configured": bool(os.getenv("PERPLEXITY_API_KEY")),
    }


@router.post("/scan")
async def scan_now():
    return await scan_news()


async def daily_news_scheduler() -> None:
    while True:
        try:
            if os.getenv("PERPLEXITY_API_KEY"):
                now = now_pacific()
                if now.hour >= 6:
                    with closing(connect_db()) as connection:
                        last = latest_scan_at(connection)
                    last_date = ""
                    if last:
                        try:
                            last_date = datetime.fromisoformat(last).astimezone(PACIFIC).date().isoformat()
                        except (ValueError, TypeError):
                            pass
                    if last_date != now.date().isoformat():
                        await scan_news(scheduled=True)
        except Exception:
            logger.exception("Scheduled RHTC news scan failed")
        await asyncio.sleep(300)


def start_daily_news_scheduler() -> asyncio.Task:
    return asyncio.create_task(daily_news_scheduler(), name="rhtc-daily-news-scan")
