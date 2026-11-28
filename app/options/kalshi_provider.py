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
    volume = numeric(m.get("volume_24h_fp"))
    interest = numeric(m.get("open_interest_fp"))
    liquidity = numeric(m.get("liquidity_dollars"))
    # Provisional provider-specific gates; contract counts are not USD turnover.
    # Require a current two-sided quote and substantive resolution rules.
    from datetime import datetime, timezone, timedelta
    try:
        observed = datetime.fromisoformat(str(m.get("updated_time")).replace("Z", "+00:00"))
        fresh = timedelta(0) <= datetime.now(timezone.utc) - observed <= timedelta(hours=1)
    except (ValueError, TypeError):
        fresh = False
    qualified = (two_sided and fresh and ask - bid <= .05
                 and min(bid_size, ask_size) >= 100
                 and volume is not None and volume >= 1000
                 and interest is not None and interest >= 1000
                 and liquidity is not None and liquidity >= 10000
                 and bool(str(m.get("rules_primary") or "").strip()))
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
        "quality": "higher liquidity" if qualified else "limited",
        "quality_policy": "kalshi-v1-provisional",
        "end_date": m.get("close_time"),
        "expected_expiration": m.get("expected_expiration_time"),
        "resolution_source": None,
        "slug": None,
        "provider_updated_at": m.get("updated_time"),
    }


async def fetch_page(client, cursor=None, *, limit=100, updated_window=None):
    if not isinstance(limit,int) or not 1 <= limit <= 1000:
        raise ValueError("Invalid Kalshi page size")
    params = {"status": "open", "limit": limit, "mve_filter": "exclude"}
    if updated_window is not None:
        lower,upper=updated_window
        if type(lower) is not int or type(upper) is not int or lower<0 or upper<lower:
            raise ValueError("Invalid Kalshi update window")
        # Do not combine metadata timestamps with status filters; closed markets
        # must also be discovered. The window excludes trading-only changes.
        params.pop("status")
        params["min_updated_ts"]=lower
        params["max_updated_ts"]=upper
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
