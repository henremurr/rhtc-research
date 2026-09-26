from __future__ import annotations

import asyncio
from contextlib import closing
import hmac
import json
import os
import random
import math
import re
import sqlite3
import secrets
import time
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any
from urllib.parse import quote

import httpx
from fastapi import FastAPI, Header, HTTPException, Query, Request
from pydantic import BaseModel, Field
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

BASE = Path(__file__).parent
app = FastAPI(title="RHTC Options Dashboard", version="0.1.0")
app.mount("/static", StaticFiles(directory=BASE / "static"), name="static")

DASHBOARD_PASSWORD_ENV = "RHTC_DASHBOARD_PASSWORD"
DASHBOARD_SESSION_COOKIE = "rhtc_dashboard_session"
DASHBOARD_SESSION_TTL = 7 * 24 * 60 * 60
DASHBOARD_PASSWORD_MIN_LENGTH = 20
_LOGIN_FAILURES: dict[str, tuple[int, float]] = {}


def configured_dashboard_password() -> str | None:
    password = os.getenv(DASHBOARD_PASSWORD_ENV, "")
    return password if len(password) >= DASHBOARD_PASSWORD_MIN_LENGTH else None


def dashboard_session_token(password: str, issued_at: int | None = None) -> str:
    timestamp = int(time.time()) if issued_at is None else int(issued_at)
    payload = f"{timestamp}.{secrets.token_urlsafe(18)}"
    signature = hmac.new(password.encode("utf-8"), payload.encode("utf-8"), "sha256").hexdigest()
    return f"{payload}.{signature}"


def valid_dashboard_session(token: str | None, password: str | None, now: int | None = None) -> bool:
    if not token or not password:
        return False
    try:
        issued_text, nonce, signature = token.split(".", 2)
        issued_at = int(issued_text)
    except (ValueError, TypeError):
        return False
    current_time = int(time.time()) if now is None else int(now)
    if issued_at > current_time or current_time - issued_at > DASHBOARD_SESSION_TTL:
        return False
    payload = f"{issued_text}.{nonce}"
    expected = hmac.new(password.encode("utf-8"), payload.encode("utf-8"), "sha256").hexdigest()
    return hmac.compare_digest(signature, expected)


def dashboard_base_path(request: Request) -> str:
    return str(request.scope.get("root_path", "")).rstrip("/") or "/options"


def dashboard_local_path(request: Request) -> str:
    path = request.scope.get("path", "/")
    root_path = str(request.scope.get("root_path", "")).rstrip("/")
    if root_path and path.startswith(root_path + "/"):
        return path[len(root_path):]
    if root_path and path == root_path:
        return "/"
    return path


def render_dashboard_login_page(base_path: str, configured: bool) -> str:
    disabled = "" if configured else " disabled"
    setup_note = (
        ""
        if configured
        else f"Set {DASHBOARD_PASSWORD_ENV} in the app's server environment to enable sign-in. Use at least {DASHBOARD_PASSWORD_MIN_LENGTH} characters."
    )
    return f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Sign in · RHTC Options</title><style>
:root{{color-scheme:light dark;--bg:#f5f4f1;--card:#fff;--ink:#233044;--muted:#748091;--gold:#927744;--line:#dce0e4}}
@media(prefers-color-scheme:dark){{:root{{--bg:#171c23;--card:#202833;--ink:#e7ecf2;--muted:#a4afbd;--line:#3b4654}}}}
*{{box-sizing:border-box}}body{{margin:0;min-height:100vh;display:grid;place-items:center;background:var(--bg);color:var(--ink);font-family:system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;padding:24px}}
.card{{width:min(420px,100%);padding:32px;border:1px solid var(--line);border-radius:14px;background:var(--card);box-shadow:0 18px 50px #00000012}}
.brand{{color:var(--gold);font-size:12px;font-weight:700;letter-spacing:1.5px}}h1{{font-size:26px;margin:10px 0 6px}}p{{color:var(--muted);font-size:14px;line-height:1.5;margin:0 0 22px}}
label{{display:block;font-size:13px;font-weight:600;margin-bottom:8px}}input{{width:100%;height:46px;padding:0 13px;border:1px solid var(--line);border-radius:8px;background:var(--bg);color:var(--ink);font:inherit}}
button{{width:100%;height:46px;margin-top:14px;border:0;border-radius:8px;background:#cfb36b;color:#171717;font-weight:700;font-size:15px;cursor:pointer}}button:disabled{{opacity:.5;cursor:not-allowed}}
#message{{min-height:22px;margin:12px 0 0;color:#b34343;font-size:13px}}.setup{{margin-top:10px;padding:11px 12px;border-radius:7px;background:#b3434312;color:#b34343;font-size:13px;line-height:1.45}}
</style></head><body><main class="card"><div class="brand">ROCKING HORSE · TRADING CO.</div><h1>Sign in</h1><p>Sign in to open the covered-call screening dashboard.</p>
<form id="login-form"><label for="password">Dashboard password</label><input id="password" name="password" type="password" autocomplete="current-password" required autofocus{disabled}>
<button id="submit" type="submit"{disabled}>Sign in</button><div id="message" role="status" aria-live="polite"></div></form>
<div class="setup" id="setup-note">{setup_note}</div>
</main><script>
const base={base_path!r};const setupNote={json.dumps(bool(setup_note))};const form=document.getElementById('login-form');
if(!setupNote)document.getElementById('setup-note').hidden=true;
form.addEventListener('submit',async event=>{{event.preventDefault();const button=document.getElementById('submit');const message=document.getElementById('message');button.disabled=true;message.textContent='';
try{{const response=await fetch(base+'/auth/login',{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify({{password:document.getElementById('password').value}})}});const data=await response.json();if(!response.ok)throw Error(data.detail||'Sign-in failed.');const target=new URLSearchParams(location.search).get('next');const safeTarget=target&&target.startsWith(base+'/')&&!target.startsWith('//')?target:base+'/';location.replace(safeTarget)}}catch(error){{message.textContent=error.message;button.disabled=false;document.getElementById('password').select()}}}});
</script></body></html>'''


@app.middleware("http")
async def require_dashboard_signin(request: Request, call_next):
    path = dashboard_local_path(request)
    public_paths = {"/login", "/auth/login", "/auth/logout"}
    if path in public_paths:
        return await call_next(request)

    base_path = dashboard_base_path(request)
    password = configured_dashboard_password()
    is_api = path == "/api" or path.startswith("/api/")
    if not password:
        if is_api or request.method not in {"GET", "HEAD"}:
            return JSONResponse({"detail": f"Dashboard sign-in is not configured. Set {DASHBOARD_PASSWORD_ENV} to a unique password with at least {DASHBOARD_PASSWORD_MIN_LENGTH} characters."}, status_code=503)
        return RedirectResponse(f"{base_path}/login", status_code=303)

    token = request.cookies.get(DASHBOARD_SESSION_COOKIE)
    if valid_dashboard_session(token, password):
        return await call_next(request)

    if is_api or request.method not in {"GET", "HEAD"}:
        return JSONResponse({"detail": "Sign in to use the RHTC options dashboard."}, status_code=401)

    original = dashboard_local_path(request)
    if original != "/" and not original.startswith("/"):
        original = "/"
    query = request.scope.get("query_string", b"").decode("latin-1")
    next_path = f"{base_path}{original}" if original != "/" else f"{base_path}/"
    if query:
        next_path += f"?{query}"
    return RedirectResponse(f"{base_path}/login?next={quote(next_path, safe='/?=&%')}", status_code=303)

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
                "symbol": symbol, "description": quote.get("description"), "peak": peak, "price": price,
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


class DashboardLoginInput(BaseModel):
    password: str = Field(min_length=1, max_length=512)


@app.get("/login")
async def dashboard_login_page(request: Request):
    response = HTMLResponse(render_dashboard_login_page(dashboard_base_path(request), configured_dashboard_password() is not None))
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    return response


@app.post("/auth/login")
async def dashboard_login(data: DashboardLoginInput, request: Request):
    expected = configured_dashboard_password()
    if not expected:
        raise HTTPException(503, f"Set {DASHBOARD_PASSWORD_ENV} to a unique password with at least {DASHBOARD_PASSWORD_MIN_LENGTH} characters.")
    client_ip = request.client.host if request.client else "unknown"
    failures, locked_until = _LOGIN_FAILURES.get(client_ip, (0, 0.0))
    if locked_until > time.monotonic():
        raise HTTPException(429, "Too many incorrect attempts. Wait 15 minutes and try again.")
    if not hmac.compare_digest(data.password.encode("utf-8"), expected.encode("utf-8")):
        failures += 1
        if client_ip not in _LOGIN_FAILURES and len(_LOGIN_FAILURES) >= 4096:
            _LOGIN_FAILURES.pop(next(iter(_LOGIN_FAILURES)))
        _LOGIN_FAILURES[client_ip] = (0, time.monotonic() + 15 * 60) if failures >= 5 else (failures, 0.0)
        raise HTTPException(401, "That password did not match. Try again.")
    _LOGIN_FAILURES.pop(client_ip, None)

    response = JSONResponse({"ok": True})
    forwarded_proto = request.headers.get("x-forwarded-proto", "").split(",", 1)[0].strip().lower()
    secure = request.url.scheme == "https" or forwarded_proto == "https"
    response.set_cookie(
        DASHBOARD_SESSION_COOKIE,
        dashboard_session_token(expected),
        max_age=DASHBOARD_SESSION_TTL,
        path=dashboard_base_path(request),
        secure=secure,
        httponly=True,
        samesite="strict",
    )
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response


@app.post("/auth/logout")
async def dashboard_logout(request: Request):
    response = JSONResponse({"ok": True})
    forwarded_proto = request.headers.get("x-forwarded-proto", "").split(",", 1)[0].strip().lower()
    secure = request.url.scheme == "https" or forwarded_proto == "https"
    response.delete_cookie(DASHBOARD_SESSION_COOKIE, path=dashboard_base_path(request), secure=secure, httponly=True, samesite="strict")
    response.headers["Cache-Control"] = "no-store"
    return response


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
        return {"symbol": symbol, "description": None, "source": "demo", "message": "Illustrative preview values; not live market data.", "rows": rows}
    provider = Tradier(token)
    try:
        rows = await provider.option_sets(symbol, item["peak"], count=4)
        description = next((r.get("description") for r in rows if r.get("description")), None)
        return {"symbol": symbol, "description": description, "source": data_source(), "rows": rows}
    except Exception as exc:
        raise HTTPException(502, f"Market data request failed: {exc}") from exc
    finally:
        await provider.close()


class SummaryInput(BaseModel):
    source: str = "demo"
    rows: list[dict[str, Any]] = Field(default_factory=list, max_length=200)


class SymbolAnalysisInput(BaseModel):
    symbol: str = Field(min_length=1, max_length=10)
    screen: dict[str, Any] = Field(default_factory=dict)


def basic_summary(rows: list[dict[str, Any]], source: str) -> str:
    valid = [r for r in rows if not r.get("error") and r.get("premium_yield") is not None]
    if not valid:
        return "No usable call quotes were returned. Check data access, symbol support, and quote freshness, then refresh."
    leaders = sorted(valid, key=lambda r: parse_number(r.get("premium_yield")), reverse=True)[:3]
    median = sorted(parse_number(r.get("premium_yield")) for r in valid)[len(valid) // 2]
    items = ", ".join(f"{r['symbol']} {parse_number(r.get('premium_yield')):.2f}% bid yield ({r.get('dte', '—')} DTE, OI {r.get('open_interest', 0)})" for r in leaders)
    label = "Illustrative preview values" if source == "demo" else "Provider quotes"
    return f"{label}: {len(valid)} call candidates are available; median bid yield is {median:.2f}%. Highest displayed ratios: {items}. These are screening metrics only. Confirm quote time, bid size, open interest, contract coverage, and the underlying before acting."


def openai_error_message(exc: Exception) -> str:
    status = getattr(exc, "status_code", None)
    code = getattr(exc, "code", None)
    body = getattr(exc, "body", None)
    if isinstance(body, dict):
        error = body.get("error", body)
        if isinstance(error, dict):
            code = error.get("code") or code
    text = str(exc).lower()
    if status == 401:
        return "OpenAI rejected the API key. Create a new key and replace OPENAI_API_KEY in Railway."
    if status == 429 and (code == "insufficient_quota" or "quota" in text or "billing" in text):
        return "OpenAI API billing or credits are unavailable. Add an API payment method or prepaid credits, then try again."
    if status == 429:
        return "OpenAI is temporarily rate limiting requests. Wait briefly and try again."
    if status == 403:
        return "This OpenAI project does not have permission to use the requested model or web search."
    if status == 400:
        return "OpenAI rejected the analysis request. Check the project model access and OPENAI_ANALYSIS_MODEL setting."
    if "timeout" in text or "timed out" in text:
        return "The OpenAI analysis timed out. Try again in a moment."
    return "ChatGPT could not complete the analysis. Try again in a moment."


def screen_only_analysis(symbol: str, screen: dict[str, Any]) -> str:
    """Return a useful contract verdict when a research response has no visible text."""
    def number(field: str) -> float | None:
        try:
            value = float(screen.get(field))
            return value if math.isfinite(value) else None
        except (TypeError, ValueError):
            return None

    price, strike = number("price"), number("strike")
    bid, ask = number("bid"), number("ask")
    bid_yield, income = number("premium_yield"), number("estimated_income")
    dte, oi, volume = number("dte"), number("open_interest"), number("volume")
    quantity = number("quantity") or 1
    cushion = ((strike - price) / price * 100) if price and strike is not None else None
    midpoint = ((bid + ask) / 2) if bid is not None and ask is not None else None
    spread = ((ask - bid) / midpoint * 100) if midpoint and bid is not None and ask is not None else None
    income_score = 4 if (bid_yield or 0) >= 2 else 3 if (bid_yield or 0) >= 1 else 2
    upside_score = 5 if (cushion or 0) >= 5 else 4 if (cushion or 0) >= 3 else 3 if (cushion or 0) >= 1 else 1
    liquidity_score = 5 if (oi or 0) >= 500 and (spread or 100) <= 10 else 4 if (oi or 0) >= 100 and (spread or 100) <= 20 else 3 if (oi or 0) >= 50 and (spread or 100) <= 30 else 2
    thin_market = (spread is not None and spread > 25) or (oi is not None and oi < 25)
    verdict = "Weak" if thin_market or income_score <= 2 or liquidity_score <= 1 else "Strong" if income_score >= 4 and upside_score >= 3 and liquidity_score >= 3 else "Mixed"
    contract = str(screen.get("contract") or "the displayed call")
    snapshot = [
        f"- **Contract:** {contract}; {int(dte)} DTE." if dte is not None else f"- **Contract:** {contract}.",
        f"- **Share price / strike:** ${price:,.2f} / ${strike:,.2f}; {cushion:.2f}% upside cushion." if price is not None and strike is not None and cushion is not None else "- **Share price / strike:** unavailable.",
        f"- **Bid / ask:** ${bid:,.2f} / ${ask:,.2f}; {spread:.1f}% quoted spread." if bid is not None and ask is not None and spread is not None else "- **Bid / ask:** unavailable.",
        f"- **Bid yield / estimated gross income:** {bid_yield:.2f}% / ${income:,.2f} for {int(quantity)} contract(s)." if bid_yield is not None and income is not None else "- **Yield / income:** unavailable.",
        f"- **Open interest / volume:** {int(oi or 0):,} / {int(volume or 0):,}.",
    ]
    assignment = "very easily" if (cushion or 0) < 1 else "fairly easily" if (cushion or 0) < 3 else "only after a more meaningful rise"
    buffer_text = f"about {bid_yield:.2f}%" if bid_yield is not None else "only the premium received"
    return (
        f"## Covered-call verdict\n**{verdict} fit (screen-only fallback).** The live quote can still be judged, "
        "but current-source company research did not finish in time.\n\n"
        f"**Scorecard — Income: {income_score}/5 · Upside cushion: {upside_score}/5 · Event risk: 3/5 · Liquidity: {liquidity_score}/5**\n\n"
        + "\n".join(snapshot)
        + "\n\n## What to verify\n- Confirm the quote is current and that the spread is acceptable.\n"
        "- Check the company’s investor-relations calendar for earnings or another major event before expiration.\n"
        "- Decide whether having the shares called away at the strike would be acceptable.\n\n"
        "## In plain English\n"
        f"This contract collects income now, but the shares could be called away {assignment} if {symbol} rises. "
        f"If the stock falls, the premium cushions only {buffer_text} of the decline; losses continue below that. "
        "The setup generally suits someone who prioritizes near-term income and is genuinely comfortable selling at the strike."
    )


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


@app.post("/api/symbol-analysis")
async def analyze_symbol(data: SymbolAnalysisInput):
    symbol = data.symbol.strip().upper()
    if not SYMBOL_PATTERN.fullmatch(symbol):
        raise HTTPException(400, "Enter a valid ticker symbol.")
    key = os.getenv("OPENAI_API_KEY")
    if not key:
        raise HTTPException(503, "ChatGPT analysis is unavailable. Configure OPENAI_API_KEY in the server settings.")

    watchlist_item = next((item for item in read_watchlist() if item["symbol"] == symbol), None)
    peak = watchlist_item["peak"] if watchlist_item else "Other"
    screen_fields = (
        "price", "change", "change_pct", "strike", "expiry", "dte", "bid", "ask",
        "premium_yield", "delta", "iv", "open_interest", "volume", "bid_size", "ask_size",
        "quote_time", "source", "contract", "quantity", "estimated_income", "ask_yield",
    )
    screen = {field: data.screen.get(field) for field in screen_fields if field in data.screen}
    screen_json = json.dumps(screen, allow_nan=False, separators=(",", ":"))
    instructions = (
        "You are the decision-support analyst inside the RHTC covered-call screener. Produce a compact, "
        "ticker-specific brief that helps a knowledgeable investor judge the DISPLAYED covered call, not a "
        "generic company profile. Use current web search and cite every material, time-sensitive claim. Verify "
        "the company matches the ticker and prioritize SEC filings, investor relations, government sources, "
        "earnings releases, and reputable financial reporting.\n\n"
        "Start with the decision, using exactly these Markdown sections:\n"
        "## Covered-call verdict\n"
        "Give a Strong / Mixed / Weak fit label and a one-sentence reason. Then show a compact scorecard with "
        "Income, Upside cushion, Event risk, and Liquidity each scored 1-5. Interpret only the supplied snapshot. "
        "For every score, 5 must mean most favorable to a covered-call seller (so Event risk 5 means low event risk). "
        "Apply strict verdict guardrails: Strong requires Income at least 4, Upside cushion at least 3, Liquidity at "
        "least 3, and no known binary event before expiration. If the bid/ask spread exceeds 25% of the midpoint or "
        "open interest is below 25, the verdict must be Weak regardless of the displayed premium. Never call a very "
        "wide spread or thin market a Strong fit. "
        "State the displayed contract, share price, strike distance in dollars and percent, bid/ask, bid yield, "
        "estimated gross income, DTE, OI/volume, and spread quality when available. Never invent missing Greeks.\n"
        "## What matters before expiration\n"
        "List only 2-4 dated catalysts or risks that could plausibly affect the stock before this contract expires. "
        "Explicitly say whether a scheduled earnings date falls before expiration; if it cannot be verified, say so.\n"
        "## Fundamental pulse\n"
        "Use 3-5 bullets covering the latest revenue growth, margins/profitability, cash/debt or dilution, guidance, "
        "and valuation only when verifiable. Favor numbers and year-over-year comparisons over narrative.\n"
        "## Bull / base / bear\n"
        "Give one concise, company-specific line for each scenario and identify what would invalidate the base case.\n"
        "## Bottom line\n"
        "In 2-3 sentences explain the premium-versus-upside tradeoff and the most important item to verify before acting.\n"
        "## In plain English\n"
        "End with one short paragraph written for a non-options expert. Translate the Strong / Mixed / Weak verdict "
        "into everyday language: say what the investor gets paid, how easily the shares could be called away, how "
        "little protection the premium provides if the stock falls, and the type of outlook this setup generally suits. "
        "Make a clear practical judgment about the contract without jargon, personalized advice, or a trade instruction.\n\n"
        "Keep the entire brief under 700 words. Omit company-history filler, methodology disclaimers, and repeated "
        "identity information. Use short bullets and bold labels. Do not print raw URLs in the prose; citations are "
        "shown separately by the application. Clearly distinguish facts from inference. Bid yield is bid divided by "
        "share price, not expected return. Do not give personalized financial advice or assume holdings/suitability."
    )
    prompt = (
        f"Analyze ticker {symbol} (RHTC theme: {peak}).\n"
        f"Current dashboard quote/options snapshot, if available: {screen_json}\n"
        "Search current public information, including the next earnings date, recent filings, guidance, and company news."
    )
    try:
        from openai import AsyncOpenAI
        client = AsyncOpenAI(api_key=key, timeout=75, max_retries=0)
        response = await client.responses.create(
            model=os.getenv("OPENAI_ANALYSIS_MODEL", os.getenv("OPENAI_MODEL", "gpt-5-mini")),
            tools=[{"type": "web_search"}],
            reasoning={"effort": "low"},
            instructions=instructions,
            input=prompt,
            # Reasoning tokens count against this budget. Reserve enough room for
            # search/reasoning plus the visible brief.
            max_output_tokens=12000,
            max_tool_calls=6,
            store=False,
        )
    except Exception as exc:
        raise HTTPException(502, openai_error_message(exc)) from exc

    citations: list[dict[str, str]] = []
    seen_urls: set[str] = set()
    for item in getattr(response, "output", []) or []:
        for content in getattr(item, "content", []) or []:
            for annotation in getattr(content, "annotations", []) or []:
                if getattr(annotation, "type", "") != "url_citation":
                    continue
                citation = getattr(annotation, "url_citation", None)
                url = getattr(citation, "url", "") if citation else ""
                title = getattr(citation, "title", "") if citation else ""
                if url.startswith("https://") and url not in seen_urls:
                    citations.append({"title": title or url, "url": url})
                    seen_urls.add(url)
    analysis = (getattr(response, "output_text", "") or "").strip()
    if not analysis:
        return {"symbol": symbol, "peak": peak, "analysis": screen_only_analysis(symbol, screen), "citations": [], "mode": "screen_fallback"}
    return {"symbol": symbol, "peak": peak, "analysis": analysis, "citations": citations, "mode": "openai"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=int(os.getenv("PORT", "8000")))
