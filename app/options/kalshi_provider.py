"""Read-only Kalshi market-data adapter. No credentials or order endpoints."""
import asyncio
import math
import httpx

URL = "https://external-api.kalshi.com/trade-api/v2/markets"


def numeric(value):
    try:
        n = float(value)
        return n if math.isfinite(n) and n >= 0 else None
    except (TypeError, ValueError):
        return None


def price(m, name):
    value = numeric(m.get(name + "_dollars"))
    return value if value is not None and value <= 1 else None


def normalize(m):
    ticker = m["ticker"]
    if not isinstance(ticker, str) or not ticker.strip():
        raise ValueError("Invalid Kalshi ticker")
    bid, ask = price(m, "yes_bid"), price(m, "yes_ask")
    bid_size, ask_size = numeric(m.get("yes_bid_size_fp")), numeric(m.get("yes_ask_size_fp"))
    two_sided = (bid is not None and ask is not None and bid <= ask
                 and bid_size is not None and ask_size is not None
                 and bid_size > 0 and ask_size > 0)
    probability = (bid + ask) / 2 if two_sided else None
    return {
        "id": "kalshi:" + ticker,
        "provider": "kalshi",
        "provider_market_id": ticker,
        "event_ticker": m.get("event_ticker"),
        "condition_id": None,
        "title": str(m.get("title") or ""),
        "description": "\n".join(str(m[k]) for k in
            ("subtitle", "yes_sub_title", "no_sub_title", "rules_primary", "rules_secondary")
            if m.get(k)),
        "probabilities": {"Yes": probability, "No": 1 - probability} if probability is not None else {},
        "probability_method": "two-sided midpoint" if two_sided else "unavailable",
        "last_price": price(m, "last_price"),
        "spread": ask - bid if two_sided else None,
        "volume24h": numeric(m.get("volume_24h_fp")),
        "volume_unit": "contracts",
        "open_interest": numeric(m.get("open_interest_fp")),
        "open_interest_unit": "contracts",
        "liquidity": numeric(m.get("liquidity_dollars")),
        "liquidity_unit": "USD",
        "quality": "limited",
        "end_date": m.get("close_time"),
        "expected_expiration": m.get("expected_expiration_time"),
        "resolution_source": None,
        "slug": None,
        "provider_updated_at": m.get("updated_time"),
    }


async def fetch_page(client, cursor=None):
    params = {"status": "open", "limit": 100, "mve_filter": "exclude"}
    if cursor:
        params["cursor"] = cursor
    for attempt in range(4):
        try:
            response = await client.get(URL, params=params)
            if response.status_code in (429, 500, 502, 503, 504) and attempt < 3:
                await asyncio.sleep(2 ** attempt)
                continue
            response.raise_for_status()
            payload = response.json()
            if not isinstance(payload, dict) or not isinstance(payload.get("markets"), list):
                raise ValueError("Unexpected Kalshi market response")
            next_cursor = payload.get("cursor")
            if not isinstance(next_cursor, str):
                raise ValueError("Missing or invalid Kalshi cursor")
            if next_cursor and (next_cursor == cursor or not payload["markets"]):
                raise ValueError("Kalshi cursor stopped advancing")
            return payload["markets"], next_cursor or None
        except httpx.TransportError:
            if attempt == 3:
                raise
            await asyncio.sleep(2 ** attempt)
