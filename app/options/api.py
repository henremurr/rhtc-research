from __future__ import annotations

import asyncio
import os
import random
import math
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import httpx
from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, Field
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

BASE = Path(__file__).parent
app = FastAPI(title="RHTC Options Dashboard", version="0.1.0")
app.mount("/static", StaticFiles(directory=BASE / "static"), name="static")

GROUPS = {
    "AI/I": "AMD ARM INTC NVDA QCOM ADI ALAB AVGO MRVL ON STM AMAT AMKR ASML GFS TER TSM MU SNDK STX WDC AAOI COHR CSCO GLW LITE SMTC AMZN CRWV DELL GOOG IBM MSFT NBIS ORCL RXT SMCI CRM PATH SNOW CRWD NET OKTA PANW INFQ IONQ QBTS QUBT RGTI AAPL META TSLA CBRS NVTS",
    "EFM/I": "CEG NNE OKLO SMR XE CCJ FISN LEU STDN UEC UUUU EQNR LNG VG ENB EPD ET KMI WMB BP COP CVX MTDR OXY SHEL TTE XOM BKR HAL BW GEV TLN BE FLNC ELMT MP SIVR USAR APD DOW LYB EROK LB TPL HNRG GFUZ TE",
    "DS/I": "LMT NOC RTX LDOS LHX AVAV AVEX KTOS ONDS RCAT UMAC AMTM PLTR BA CW GE HII FLY RDW RKLB SPCX ASTS PL YSS",
    "Other": "HOOD PG",
}
WATCHLIST = [{"symbol": s, "peak": peak} for peak, symbols in GROUPS.items() for s in symbols.split()]

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
    strike = math.ceil((price * (1 + rng.uniform(.015, .09))) / 5) * 5
    expiry = expiry_override or date.today() + timedelta(days=rng.choice([12, 19, 26, 33, 40]))
    bid = round(max(.05, price * rng.uniform(.006, .035)), 2)
    ask = round(bid + rng.uniform(.03, .30), 2)
    return {
        "symbol": symbol, "peak": peak, "price": price, "change_pct": round(rng.uniform(-3.4, 4.1), 2),
        "strike": strike, "expiry": expiry.isoformat(), "dte": (expiry - date.today()).days,
        "bid": bid, "ask": ask, "mid": round((bid + ask) / 2, 2),
        "premium_yield": round(bid / price * 100, 2), "delta": round(rng.uniform(.18, .42), 2),
        "iv": round(rng.uniform(28, 92), 1), "open_interest": rng.choice([0, 18, 74, 135, 420, 1270]),
        "volume": rng.choice([0, 2, 17, 53, 186]), "bid_size": rng.choice([1, 3, 10, 22]), "ask_size": rng.choice([1, 4, 12, 25]), "quote_time": "DEMO DATA",
        "contract": f"{symbol} {expiry:%b %d} ${strike:g} C", "source": "demo",
    }


def parse_number(value: Any, default: float = 0.0) -> float:
    try:
        return float(value) if value is not None else default
    except (TypeError, ValueError):
        return default


class Tradier:
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

    async def option_sets(self, symbol: str, peak: str, count: int = 4) -> list[dict[str, Any]]:
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
        future = sorted(d for d in dates if d and date.fromisoformat(d) >= today)
        if not future:
            raise ValueError("No future expiration returned")
        expiry_window = future[:max(1, min(max(count, 12), len(future)))]

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
                "change_pct": parse_number(quote.get("change_percentage")),
                "strike": parse_number(selected.get("strike")), "expiry": expiry,
                "dte": (exp - today).days, "bid": bid, "ask": ask,
                "mid": round((bid + ask) / 2, 2), "premium_yield": round(bid / price * 100, 2),
                "delta": parse_number(g.get("delta")), "iv": (parse_number(g.get("mid_iv")) * 100 if abs(parse_number(g.get("mid_iv"))) <= 5 else parse_number(g.get("mid_iv"))),
                "open_interest": int(parse_number(selected.get("open_interest"))),
                "volume": int(parse_number(selected.get("volume"))),
                "bid_size": int(parse_number(selected.get("bidsize"))), "ask_size": int(parse_number(selected.get("asksize"))),
                "quote_time": quote.get("trade_date") or quote.get("ask_date") or "provider timestamp unavailable",
                "contract": selected.get("symbol", f"{symbol} {expiry} ${selected.get('strike')} C"),
                "source": "tradier",
            }

        rows = []
        for expiry in expiry_window:
            row = await nearest_call(expiry)
            if row is not None:
                rows.append(row)
            if len(rows) >= count:
                break
        if not rows:
            raise ValueError("No out-of-the-money calls returned for the next available expirations")
        return rows

    async def one(self, symbol: str, peak: str) -> dict[str, Any]:
        return (await self.option_sets(symbol, peak, count=1))[0]

    async def close(self) -> None:
        await self.client.aclose()


@app.get("/")
async def home():
    return FileResponse(BASE / "templates" / "index.html")


@app.get("/api/health")
async def health():
    return {"ok": True, "provider": data_source(), "watchlist_count": len(WATCHLIST)}


def data_source() -> str:
    if not os.getenv("TRADIER_API_TOKEN"):
        return "demo"
    return "tradier_sandbox" if "sandbox.tradier.com" in os.getenv("TRADIER_BASE_URL", "https://sandbox.tradier.com/v1") else "tradier"


@app.get("/api/watchlist")
async def get_watchlist(peak: str | None = None, q: str | None = None):
    rows = WATCHLIST
    if peak and peak != "All Peaks":
        rows = [r for r in rows if r["peak"] == peak]
    if q:
        rows = [r for r in rows if q.upper() in r["symbol"]]
    return {"rows": rows, "count": len(rows)}


@app.get("/api/opportunities")
async def opportunities(
    peak: str = "All Peaks", q: str = "", sort: str = "premium_yield",
    limit: int = Query(default=25, ge=1, le=len(WATCHLIST)),
):
    selected = [r for r in WATCHLIST if (peak == "All Peaks" or r["peak"] == peak) and q.upper() in r["symbol"]][:limit]
    token = os.getenv("TRADIER_API_TOKEN")
    if token and data_source() == "tradier_sandbox":
        limit = min(limit, 10)
        selected = selected[:limit]
    if not token:
        rows = [demo_row(r["symbol"], r["peak"]) for r in selected]
        source = "demo"
    else:
        provider = Tradier(token)
        sem = asyncio.Semaphore(3)
        async def guarded(item: dict[str, str]):
            async with sem:
                try:
                    return await provider.one(item["symbol"], item["peak"])
                except Exception as exc:
                    return {**item, "error": str(exc), "source": "error"}
        try:
            rows = await asyncio.gather(*(guarded(r) for r in selected))
        finally:
            await provider.close()
        source = data_source()
    for row in rows:
        row["coverage_status"] = "Needs review" if row.get("open_interest", 0) < 25 else "Liquid enough to review"
    rows.sort(key=lambda row: parse_number(row.get(sort)), reverse=(sort != "dte"))
    return {"rows": rows, "count": len(rows), "total": len(WATCHLIST), "source": source, "as_of": utc_now().isoformat()}


@app.get("/api/chain/{symbol}")
async def chain(symbol: str):
    symbol = symbol.upper()
    item = next((r for r in WATCHLIST if r["symbol"] == symbol), None)
    if not item:
        raise HTTPException(404, "Symbol is not in the RHTC watchlist")
    token = os.getenv("TRADIER_API_TOKEN")
    if not token:
        today = date.today()
        rows = [
            demo_row(symbol, item["peak"], expiry_override=today + timedelta(days=12 + 7 * i), seed_offset=i)
            for i in range(4)
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
    rows: list[dict[str, Any]] = Field(default_factory=list, max_length=127)


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
