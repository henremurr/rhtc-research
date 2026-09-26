from __future__ import annotations

import asyncio
from contextlib import closing
import hmac
import os
import random
import math
import re
import sqlite3
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

import httpx
from fastapi import FastAPI, Header, HTTPException, Query
from pydantic import BaseModel, Field
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

BASE = Path(__file__).parent
app = FastAPI(title="RHTC Options Dashboard", version="0.1.0")
app.mount("/static", StaticFiles(directory=BASE / "static"), name="static")

GROUPS = {
    "AI/I": "AMD ARM INTC NVDA QCOM ADI ALAB AVGO MRVL ON STM AMAT AMKR ASML GFS TER TSM MU SNDK STX WDC AAOI COHR CSCO GLW LITE SMTC AMZN CRWV DELL GOOG IBM MSFT NBIS ORCL RXT SMCI CRM PATH SNOW CRWD NET OKTA PANW INFQ IONQ QBTS QUBT RGTI AAPL META TSLA CBRS NVTS",
    "EFM/I": "CEG NNE OKLO SMR XE CCJ FISN LEU STDN UEC UUUU EQNR LNG VG ENB EPD ET KMI WMB BP COP CVX MTDR OXY SHEL TTE XOM BKR HAL BW GEV TLN BE FLNC ELMT MP SIVR USAR APD DOW LYB EROK LB TPL HNRG GFUZ TE",
    "DS/I": "LMT NOC RTX LDOS LHX AVAV AVEX KTOS ONDS RCAT UMAC AMTM PLTR BA CW GE HII FLY RDW RKLB SPCX ASTS PL YSS XTND OPTX",
    "Other": "HOOD PG",
}
WATCHLIST = [{"symbol": s, "peak": peak} for peak, symbols in GROUPS.items() for s in symbols.split()]
VALID_PEAKS = {"AI/I", "EFM/I", "DS/I", "Other"}
SYMBOL_PATTERN = re.compile(r"^[A-Z][A-Z0-9.-]{0,9}$")


def watchlist_db_path() -> Path:
    data_dir = Path(os.getenv("RHTC_DATA_DIR", str(BASE.parent.parent / "data")))
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir / "rhtc_symbols.sqlite3"


def connect_watchlist_db() -> sqlite3.Connection:
    connection = sqlite3.connect(watchlist_db_path(), timeout=15)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("CREATE TABLE IF NOT EXISTS symbols (position INTEGER PRIMARY KEY, symbol TEXT NOT NULL UNIQUE, peak TEXT NOT NULL, share_price REAL, quantity REAL)")
    columns = {row["name"] for row in connection.execute("PRAGMA table_info(symbols)")}
    if "share_price" not in columns:
        connection.execute("ALTER TABLE symbols ADD COLUMN share_price REAL")
    if "quantity" not in columns:
        connection.execute("ALTER TABLE symbols ADD COLUMN quantity REAL")
    connection.execute("CREATE TABLE IF NOT EXISTS app_state (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
    connection.execute("INSERT OR IGNORE INTO app_state(key, value) VALUES ('watchlist_seeded', '0')")
    seeded = connection.execute("SELECT value FROM app_state WHERE key = 'watchlist_seeded'").fetchone()
    if seeded and seeded["value"] != "1":
        connection.executemany("INSERT INTO symbols(position, symbol, peak, share_price, quantity) VALUES (?, ?, ?, ?, ?)", [(i, row["symbol"], row["peak"], None, None) for i, row in enumerate(WATCHLIST)])
        connection.execute("INSERT OR REPLACE INTO app_state(key, value) VALUES ('watchlist_seeded', '1')")
    connection.execute("INSERT OR IGNORE INTO app_state(key, value) VALUES ('legacy_import_open', '1')")
    connection.commit()
    return connection


def read_watchlist() -> list[dict[str, Any]]:
    with closing(connect_watchlist_db()) as connection:
        return [dict(row) for row in connection.execute("SELECT symbol, peak, share_price, quantity FROM symbols ORDER BY position")]


def optional_nonnegative_number(item: dict[str, Any], field: str) -> int | float | None:
    value = item.get(field)
    if value is None:
        return None
    if isinstance(value, str):
        value = value.strip()
        if value == "":
            return None
    if isinstance(value, bool):
        raise HTTPException(400, f"{field.replace('_', ' ').title()} must be a non-negative number or blank.")
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise HTTPException(400, f"{field.replace('_', ' ').title()} must be a non-negative number or blank.")
    if not math.isfinite(number) or number < 0:
        raise HTTPException(400, f"{field.replace('_', ' ').title()} must be a non-negative number or blank.")
    return int(number) if number.is_integer() else number


def validate_watchlist(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if len(rows) > 200:
        raise HTTPException(400, "The watchlist can contain at most 200 symbols.")
    cleaned: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in rows:
        ticker = str(item.get("symbol", "")).strip().upper()
        peak = str(item.get("peak", "Other"))
        if not SYMBOL_PATTERN.fullmatch(ticker) or peak not in VALID_PEAKS or ticker in seen:
            raise HTTPException(400, "Use unique ticker symbols and a valid Three Peaks category.")
        seen.add(ticker)
        cleaned.append({
            "symbol": ticker,
            "peak": peak,
            "share_price": optional_nonnegative_number(item, "share_price"),
            "quantity": optional_nonnegative_number(item, "quantity"),
        })
    return cleaned


def watchlist_storage_ready() -> bool:
    data_dir = os.getenv("RHTC_DATA_DIR")
    volume_mount = os.getenv("RAILWAY_VOLUME_MOUNT_PATH")
    if not data_dir or not volume_mount:
        return False
    return Path(data_dir).resolve() == Path(volume_mount).resolve()


def replace_watchlist(rows: list[dict[str, Any]]) -> None:
    with closing(connect_watchlist_db()) as connection:
        connection.execute("DELETE FROM symbols")
        connection.executemany(
            "INSERT INTO symbols(position, symbol, peak, share_price, quantity) VALUES (?, ?, ?, ?, ?)",
            [(i, row["symbol"], row["peak"], row["share_price"], row["quantity"]) for i, row in enumerate(rows)],
        )
        connection.execute("INSERT OR REPLACE INTO app_state(key, value) VALUES ('legacy_import_open', '0')")
        connection.commit()


def require_watchlist_admin(token: str | None) -> None:
    expected = os.getenv("RHTC_WATCHLIST_ADMIN_TOKEN")
    if not expected:
        raise HTTPException(503, "Set RHTC_WATCHLIST_ADMIN_TOKEN in Railway Variables before editing the shared list.")
    if not os.getenv("RHTC_DATA_DIR"):
        raise HTTPException(503, "Attach a Railway Volume at /data and set RHTC_DATA_DIR=/data before editing the shared list.")
    if not watchlist_storage_ready():
        raise HTTPException(503, "Railway does not report a Volume mounted at RHTC_DATA_DIR. Attach the Volume at /data and redeploy.")
    if not token or not hmac.compare_digest(token, expected):
        raise HTTPException(401, "The RHTC watchlist admin token is missing or incorrect.")

# Illustrative prices and option values are generated for UI testing only.
# They are never labeled as live; set TRADIER_API_TOKEN to fetch provider data.
SEED_PRICES = {
    "NVDA": 181.40, "AMD": 164.20, "AVGO": 332.10, "MRVL": 91.70,
    "MU": 128.60, "ORCL": 241.30, "OKLO": 92.80, "CCJ": 74.10,
    "ET": 18.90, "VG": 17.20, "LMT": 478.50, "NOC": 531.40,
    "RTX": 161.20, "AVAV": 216.70, "KTOS": 58.20, "PLTR": 137.80,
    "RKLB": 39.10, "RDW": 12.60, "UMAC": 18.40, "ASTS": 46.70,
    "GE": 242.80, "BA": 203.50, "HOOD": 92.10, "PG": 164.30,
}


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def format_option_contract(expiry: str | date, strike: Any) -> str:
    expiry_date = expiry if isinstance(expiry, date) else date.fromisoformat(expiry)
    strike_text = format(Decimal(str(strike)).normalize(), "f")
    if "." in strike_text:
        strike_text = strike_text.rstrip("0").rstrip(".")
    if "." not in strike_text:
        strike_text += ".0"
    return f"{expiry_date:%Y%m%d}-{strike_text}"


def demo_row(
    symbol: str,
    peak: str,
    *,
    expiry_override: date | None = None,
    seed_offset: int = 0,
) -> dict[str, Any]:
    seed = sum((i + 1) * ord(c) for i, c in enumerate(symbol))
    seed += seed_offset * 997
    rng = random.Random(seed)
    price = SEED_PRICES.get(symbol, round(rng.uniform(8, 250), 2))
    change_pct = round(rng.uniform(-3.4, 4.1), 2)
    change = round(price * change_pct / (100 + change_pct), 2)
    strike = math.ceil((price * (1 + rng.uniform(.015, .09))) / 5) * 5
    expiry = expiry_override or date.today() + timedelta(days=rng.choice([12, 19, 26, 33, 40]))
    bid = round(max(.05, price * rng.uniform(.006, .035)), 2)
    ask = round(bid + rng.uniform(.03, .30), 2)
    return {
        "symbol": symbol, "peak": peak, "price": price, "change": change, "change_pct": change_pct,
        "strike": strike, "expiry": expiry.isoformat(), "dte": (expiry - date.today()).days,
        "bid": bid, "ask": ask, "mid": round((bid + ask) / 2, 2),
        "premium_yield": round(bid / price * 100, 2), "delta": round(rng.uniform(.18, .42), 2),
        "iv": round(rng.uniform(28, 92), 1), "open_interest": rng.choice([0, 18, 74, 135, 420, 1270]),
        "volume": rng.choice([0, 2, 17, 53, 186]), "bid_size": rng.choice([1, 3, 10, 22]), "ask_size": rng.choice([1, 4, 12, 25]), "quote_time": "DEMO DATA",
        "contract": format_option_contract(expiry, strike), "source": "demo",
    }


def parse_number(value: Any, default: float = 0.0) -> float:
    try:
        return float(value) if value is not None else default
    except (TypeError, ValueError):
        return default


class Tradier:
    DTE_WINDOWS = ((0, 7), (8, 14), (15, 21), (22, None))

    def __init__(self, token: str):
        self.client = httpx.AsyncClient(
            base_url=os.getenv("TRADIER_BASE_URL", "https://sandbox.tradier.com/v1"),
            headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
            timeout=20,
        )

    async def get(self, path: str, params: dict[str, Any]) -> dict[str, Any]:
        response = await self.client.get(path, params=params)
        response.raise_for_status()
        return response.json()

    async def option_sets(self, symbol: str, peak: str, count: int = 4, only_set: int | None = None) -> list[dict[str, Any]]:
        qdata = await self.get("/markets/quotes", {"symbols": symbol})
        quote = qdata.get("quotes", {}).get("quote", {})
        if isinstance(quote, list):
            quote = quote[0] if quote else {}
        price = parse_number(quote.get("last")) or parse_number(quote.get("close"))
        if price <= 0:
            raise ValueError("No underlying price returned")

        edata = await self.get("/markets/options/expirations", {"symbol": symbol, "includeAllRoots": "false"})
        expiration_data = edata.get("expirations", {})
        dates = expiration_data.get("date", []) if isinstance(expiration_data, dict) else expiration_data
        if isinstance(dates, str):
            dates = [dates]
        today = date.today()
        future = []
        for expiry in dates:
            try:
                dte = (date.fromisoformat(expiry) - today).days
            except (TypeError, ValueError):
                continue
            if dte >= 0:
                future.append((expiry, dte))
        future.sort(key=lambda item: item[1])

        async def nearest_call(expiry: str) -> dict[str, Any] | None:
            cdata = await self.get("/markets/options/chains", {"symbol": symbol, "expiration": expiry, "greeks": "true"})
            contracts = cdata.get("options", {}).get("option", [])
            if isinstance(contracts, dict):
                contracts = [contracts]
            calls = [c for c in contracts if c.get("option_type") == "call" and parse_number(c.get("strike")) > price]
            calls = [c for c in calls if parse_number(c.get("bid")) >= 0]
            if not calls:
                return None
            selected = min(calls, key=lambda c: parse_number(c.get("strike")) - price)
            bid, ask = parse_number(selected.get("bid")), parse_number(selected.get("ask"))
            g = selected.get("greeks") or {}
            exp = date.fromisoformat(expiry)
            return {
                "symbol": symbol, "peak": peak, "price": price,
                "change": parse_number(quote.get("change"), price - parse_number(quote.get("prevclose"), price)),
                "change_pct": parse_number(quote.get("change_percentage")),
                "strike": parse_number(selected.get("strike")), "expiry": expiry,
                "dte": (exp - today).days, "bid": bid, "ask": ask,
                "mid": round((bid + ask) / 2, 2), "premium_yield": round(bid / price * 100, 2),
                "delta": parse_number(g.get("delta")), "iv": (parse_number(g.get("mid_iv")) * 100 if abs(parse_number(g.get("mid_iv"))) <= 5 else parse_number(g.get("mid_iv"))),
                "open_interest": int(parse_number(selected.get("open_interest"))),
                "volume": int(parse_number(selected.get("volume"))),
                "bid_size": int(parse_number(selected.get("bidsize"))), "ask_size": int(parse_number(selected.get("asksize"))),
                "quote_time": quote.get("trade_date") or quote.get("ask_date") or "provider timestamp unavailable",
                "contract": format_option_contract(expiry, selected.get("strike")),
                "source": "tradier",
            }

        rows = []
        selected_windows = (
            [self.DTE_WINDOWS[only_set - 1]]
            if only_set is not None
            else self.DTE_WINDOWS[:max(1, min(count, 4))]
        )
        for minimum, maximum in selected_windows:
            label = f"{minimum}+ DTE" if maximum is None else f"{minimum}-{maximum} DTE"
            eligible = [expiry for expiry, dte in future if dte >= minimum and (maximum is None or dte <= maximum)]
            row = None
            for expiry in eligible:
                row = await nearest_call(expiry)
                if row is not None:
                    break
            if row is None:
                reason = f"No listed expiration in {label} window" if not eligible else f"No out-of-the-money call found in {label} window"
                rows.append({"symbol": symbol, "peak": peak, "dte_window": label, "error": reason, "source": "error"})
            else:
                row["dte_window"] = label
                rows.append(row)
        return rows

    async def one(self, symbol: str, peak: str, expiration_set: int = 1) -> dict[str, Any]:
        rows = await self.option_sets(symbol, peak, only_set=expiration_set)
        row = rows[0]
        if row.get("error"):
            raise ValueError(row["error"])
        return row

    async def close(self) -> None:
        await self.client.aclose()


@app.get("/")
async def home():
    return FileResponse(BASE / "templates" / "index.html")


class WatchlistUpdate(BaseModel):
    rows: list[dict[str, Any]] = Field(default_factory=list, max_length=200)


@app.get("/api/health")
async def health():
    return {"ok": True, "provider": data_source(), "watchlist_count": len(read_watchlist())}


def data_source() -> str:
    if not os.getenv("TRADIER_API_TOKEN"):
        return "demo"
    return "tradier_sandbox" if "sandbox.tradier.com" in os.getenv("TRADIER_BASE_URL", "https://sandbox.tradier.com/v1") else "tradier"


@app.get("/api/watchlist")
async def get_watchlist(peak: str | None = None, q: str | None = None):
    rows = read_watchlist()
    if peak and peak != "All Peaks":
        rows = [r for r in rows if r["peak"] == peak]
    if q:
        rows = [r for r in rows if q.upper() in r["symbol"]]
    with closing(connect_watchlist_db()) as connection:
        state = connection.execute("SELECT value FROM app_state WHERE key = 'legacy_import_open'").fetchone()
    return {
        "rows": rows,
        "count": len(rows),
        "migration_open": bool(state and state["value"] == "1"),
        "editing_enabled": bool(os.getenv("RHTC_WATCHLIST_ADMIN_TOKEN") and watchlist_storage_ready()),
    }


@app.put("/api/watchlist")
async def update_watchlist(data: WatchlistUpdate, x_rhtc_admin_token: str | None = Header(default=None)):
    require_watchlist_admin(x_rhtc_admin_token)
    rows = validate_watchlist(data.rows)
    replace_watchlist(rows)
    return {"rows": rows, "count": len(rows)}


@app.get("/api/opportunities")
async def opportunities(
    peak: str = "All Peaks", q: str = "", sort: str = "income",
    limit: int = Query(default=25, ge=1, le=200),
    expiration_set: int = Query(default=1, ge=1, le=4),
    holdings_only: bool = False,
    max_last: float | None = Query(default=None, ge=0),
):
    universe = read_watchlist()
    selected = [
        r for r in universe
        if (peak == "All Peaks" or r["peak"] == peak)
        and q.upper() in r["symbol"]
        and (not holdings_only or (r.get("share_price") is not None and r.get("quantity") is not None))
    ][:limit]
    token = os.getenv("TRADIER_API_TOKEN")
    if not token:
        days = (7, 14, 21, 28)
        expiry = date.today() + timedelta(days=days[expiration_set - 1])
        rows = [demo_row(r["symbol"], r["peak"], expiry_override=expiry, seed_offset=expiration_set - 1) for r in selected]
        source = "demo"
    else:
        provider = Tradier(token)
        sem = asyncio.Semaphore(3)
        async def guarded(item: dict[str, str]):
            async with sem:
                try:
                    return await provider.one(item["symbol"], item["peak"], expiration_set)
                except Exception as exc:
                    return {**item, "error": str(exc), "source": "error"}
        try:
            rows = await asyncio.gather(*(guarded(r) for r in selected))
        finally:
            await provider.close()
        source = data_source()
    for row in rows:
        holding = next((item for item in selected if item["symbol"] == row.get("symbol")), {})
        row["share_price"] = holding.get("share_price")
        row["quantity"] = holding.get("quantity")
        row["coverage_status"] = "Needs review" if row.get("open_interest", 0) < 25 else "Liquid enough to review"
    if max_last is not None:
        rows = [
            row for row in rows
            if not row.get("error")
            and row.get("price") is not None
            and math.isfinite(parse_number(row.get("price"), math.nan))
            and parse_number(row.get("price"), math.nan) <= max_last
        ]
    if sort == "income":
        rows.sort(
            key=lambda row: ((parse_number(row.get("bid")) + parse_number(row.get("ask"))) / 2) * 100,
            reverse=True,
        )
    else:
        rows.sort(key=lambda row: parse_number(row.get(sort)), reverse=(sort != "dte"))
    return {"rows": rows, "count": len(rows), "total": len(universe), "source": source, "as_of": utc_now().isoformat()}


@app.get("/api/chain/{symbol}")
async def chain(symbol: str):
    symbol = symbol.upper()
    item = next((r for r in read_watchlist() if r["symbol"] == symbol), None)
    if not item:
        if not SYMBOL_PATTERN.fullmatch(symbol):
            raise HTTPException(404, "Invalid ticker symbol")
        item = {"symbol": symbol, "peak": "Other"}
    token = os.getenv("TRADIER_API_TOKEN")
    if not token:
        today = date.today()
        rows = [
            demo_row(symbol, item["peak"], expiry_override=today + timedelta(days=days), seed_offset=i)
            for i, days in enumerate((7, 14, 21, 28))
        ]
        return {"symbol": symbol, "source": "demo", "message": "Illustrative preview values; not live market data.", "rows": rows}
    provider = Tradier(token)
    try:
        rows = await provider.option_sets(symbol, item["peak"], count=4)
        return {"symbol": symbol, "source": data_source(), "rows": rows}
    except Exception as exc:
        raise HTTPException(502, f"Market data request failed: {exc}") from exc
    finally:
        await provider.close()


class SummaryInput(BaseModel):
    source: str = "demo"
    rows: list[dict[str, Any]] = Field(default_factory=list, max_length=200)


def basic_summary(rows: list[dict[str, Any]], source: str) -> str:
    valid = [r for r in rows if not r.get("error") and r.get("premium_yield") is not None]
    if not valid:
        return "No usable call quotes were returned. Check data access, symbol support, and quote freshness, then refresh."
    leaders = sorted(valid, key=lambda r: parse_number(r.get("premium_yield")), reverse=True)[:3]
    median = sorted(parse_number(r.get("premium_yield")) for r in valid)[len(valid) // 2]
    items = ", ".join(f"{r['symbol']} {parse_number(r.get('premium_yield')):.2f}% bid yield ({r.get('dte', '—')} DTE, OI {r.get('open_interest', 0)})" for r in leaders)
    label = "Illustrative preview values" if source == "demo" else "Provider quotes"
    return f"{label}: {len(valid)} call candidates are available; median bid yield is {median:.2f}%. Highest displayed ratios: {items}. These are screening metrics only. Confirm quote time, bid size, open interest, contract coverage, and the underlying before acting."


@app.post("/api/summary")
async def summarize(data: SummaryInput):
    rows = data.rows
    key = os.getenv("OPENAI_API_KEY")
    if not key:
        return {"mode": "rules", "summary": basic_summary(rows, data.source)}
    try:
        from openai import AsyncOpenAI
        client = AsyncOpenAI(api_key=key)
        payload = [{k: r.get(k) for k in ("symbol", "peak", "price", "strike", "expiry", "dte", "bid", "ask", "premium_yield", "delta", "iv", "open_interest", "volume", "bid_size", "ask_size", "quote_time", "error")} for r in rows]
        response = await client.responses.create(
            model=os.getenv("OPENAI_MODEL", "gpt-5-mini"),
            instructions=("Write a concise internal market-data screen note using only supplied rows. "
                "Describe what stands out and the data limitations. Do not give buy, sell, roll, or trade instructions; "
                "do not infer the user's holdings or suitability. Treat nulls and errors as missing data. "
                "Mention that bid-yield is bid divided by share price and is not an expected return. "
                "If data source is demo, prominently state that all values are illustrative, not live."),
            input=f"Source: {data.source}. Options rows (JSON): {payload}",
            max_output_tokens=240,
        )
        text = response.output_text.strip() or basic_summary(rows, data.source)
        return {"mode": "openai", "summary": text}
    except Exception:
        return {"mode": "rules", "summary": basic_summary(rows, data.source)}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=int(os.getenv("PORT", "8000")))
