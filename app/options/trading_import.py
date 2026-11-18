"""Fidelity account history import for the authenticated options dashboard."""
import csv
import hashlib
import io
import json
import re
import sqlite3
from collections import Counter
from contextlib import closing
from datetime import datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from fastapi import HTTPException, Request
from fastapi.responses import HTMLResponse, Response
from .trade_pdf import build_report
from starlette.concurrency import run_in_threadpool

HEADERS = ["Run Date", "Action", "Symbol", "Description", "Type", "Price ($)", "Quantity",
           "Commission ($)", "Fees ($)", "Accrued Interest ($)", "Amount ($)", "Cash Balance ($)", "Settlement Date"]
COLUMNS = "trade_date,action,symbol,description,account_type,price,quantity,commission,fees,interest,amount,cash_balance,settlement_date"
LIMIT = 8 * 1024 * 1024


# Each list follows the database's canonical column order. None means the
# export does not supply that field. Combined Schwab fees stay in fees.
FORMATS = {
    "Fidelity": HEADERS,
    "Fidelity IRA": [None if name == "Cash Balance ($)" else name for name in HEADERS],
    "Schwab": ["Date", "Action", "Symbol", "Description", None, "Price", "Quantity",
               None, "Fees & Comm", None, "Amount", None, None],
    "Vanguard": ["Trade Date", "Transaction Type", "Symbol", "Investment Name", "Account Type",
                 "Share Price", "Shares", "Commissions", "Fees", "Accrued Interest",
                 "Net Amount", None, "Settlement Date"],
}


def import_history(path, account, payload, broker="Fidelity"):
    if broker not in FORMATS:
        raise ValueError("Choose Fidelity, Fidelity IRA, Schwab, or Vanguard.")
    mapping = FORMATS[broker]
    embedded = broker == "Fidelity IRA"
    reader = csv.reader(io.StringIO(payload.decode("utf-8-sig")), strict=True)
    for header in reader:
        header = [name.strip() for name in header]
        if all(name in header for name in mapping if name) and (not embedded or "Account Number" in header):
            break
    else:
        raise ValueError(f"The file does not contain the expected {broker} transaction-history columns. Check the selected format.")
    positions = [header.index(name) if name else None for name in mapping]
    account_column = header.index("Account Number") if embedded else None
    counts = Counter()
    records = []
    for row in reader:
        if not row or (len(row) == 1 and not re.match(r"^\d", row[0])):
            continue
        if len(row) != len(header):
            raise ValueError(f"Unexpected column count at line {reader.line_num}.")
        if embedded:
            account = row[account_column].strip().upper()
            if not re.fullmatch(r"[A-Z0-9_-]{1,40}", account):
                raise ValueError(f"Invalid account number at line {reader.line_num}.")
        row = [row[i].strip() if i is not None else "" for i in positions]
        try:
            row[0] = datetime.strptime(row[0], "%m/%d/%Y").date().isoformat()
            if row[12]:
                row[12] = datetime.strptime(row[12], "%m/%d/%Y").date().isoformat()
            for i in range(5, 11):
                if row[i]:
                    number = Decimal(row[i].replace(",", "").replace("$", "").replace("(", "-").replace(")", ""))
                    if not number.is_finite():
                        raise ValueError()
                    row[i] = format(number.normalize(), "f")
        except (ValueError, InvalidOperation):
            raise ValueError(f"Invalid date or number at line {reader.line_num}.") from None
        # Balance and settlement status can change between exports. Occurrence
        # counts preserve separate identical fills in the same account history.
        key = hashlib.sha256(json.dumps(row[:11] if broker in ("Fidelity", "Fidelity IRA") else [broker, *row[:11]], ensure_ascii=False).encode()).hexdigest()
        counts[account, key] += 1
        records.append((account, key, counts[account, key], *row, broker))
    if not records:
        raise ValueError("No transactions found.")
    with closing(sqlite3.connect(path, timeout=20)) as db, db:
        db.execute("BEGIN IMMEDIATE")
        db.execute("""CREATE TABLE IF NOT EXISTS trading_transactions (
            account TEXT NOT NULL, fingerprint TEXT NOT NULL, occurrence INTEGER NOT NULL,
            trade_date TEXT, action TEXT, symbol TEXT, description TEXT, account_type TEXT,
            price NUMERIC, quantity NUMERIC, commission NUMERIC, fees NUMERIC, interest NUMERIC,
            amount NUMERIC, cash_balance TEXT, settlement_date TEXT,
            PRIMARY KEY(account, fingerprint, occurrence))""")
        if "broker" not in {col[1] for col in db.execute("PRAGMA table_info(trading_transactions)")}:
            db.execute("ALTER TABLE trading_transactions ADD COLUMN broker TEXT NOT NULL DEFAULT 'Fidelity'")
        db.execute("CREATE INDEX IF NOT EXISTS trading_account_date ON trading_transactions(account, trade_date, symbol)")
        db.executemany(f"INSERT INTO trading_transactions(account,fingerprint,occurrence,{COLUMNS},broker) VALUES ({','.join(['?']*17)}) ON CONFLICT(account,fingerprint,occurrence) DO NOTHING", records)
        inserted = db.total_changes
        return {"added": inserted, "skipped": len(records) - inserted}


def trade_kind(action, symbol, description):
    option = re.search(r"\d{6}([CP])\d", symbol or "", re.I)
    words = f"{action} {description or ''}"
    call = option[1].upper() == "C" if option else bool(re.search(r"\bCALL\b", words, re.I))
    bought = re.search(r"\b(buy|bought|purchase|purchased)\b", action, re.I)
    sold = re.search(r"\b(sell|sold|sale)\b", action, re.I)
    if call and bought:
        return "call_buy"
    if call and sold and re.search(r"\b(open|opening)\b", action, re.I):
        return "call_write"
    if not call and not option and not re.search(r"\b(call|put)\b", description or "", re.I):
        if bought:
            return "stock_buy"
        if sold:
            return "stock_sell"


def order_same_day(entries):
    # Reorder only the slots occupied by each affected pair.
    for first, second in (("stock_buy", "call_write"), ("call_buy", "stock_sell")):
        slots = [i for i, (kind, _) in enumerate(entries) if kind in (first, second)]
        ordered = sorted((entries[i] for i in slots), key=lambda entry: entry[0] == second)
        for i, entry in zip(slots, ordered):
            entries[i] = entry
    return entries


def trade_rows(db, account, year, summaries=None):
    rows = db.execute("""
        SELECT trade_date, action, symbol, description, quantity, price, amount
        FROM trading_transactions
        WHERE account=?
        ORDER BY trade_date, rowid
    """, (account,))
    groups = {}
    for day, action, symbol, description, quantity, price, amount in rows:
        if not symbol and re.search(r"\b(card|debit|merchant|payment)\b", action, re.I):
            continue
        if not re.search(r"\b(buy|bought|sell|sold|sale|purchase|purchased|assigned|assignment|expired|expiration|exercise|exercised|reinvest\w*)\b", action, re.I):
            continue
        contract = re.match(r"^-?([A-Z.]+)\s*\d{6}[CP]", symbol or "", re.I)
        ticker = contract[1] if contract else (symbol or "").split(" ")[0]
        kind = trade_kind(action, symbol, description)
        if contract and re.search(r"\b(expired|expiration|assigned|assignment)\b", action, re.I):
            kind = "call_end"
        elif kind == "call_buy" and re.search(r"\b(open|opening)\b", action, re.I):
            kind = None
        days = groups.setdefault(ticker or "Unspecified ticker", {})
        days.setdefault(day, []).append((kind,
                                        [day, action, symbol, quantity, price, amount]))
    result = {}
    for ticker, days in sorted(groups.items()):
        entries = [entry for day_entries in days.values() for entry in order_same_day(day_entries)]
        visible = [(kind, row) for kind, row in entries if not year or row[0][:4] == str(year)]
        if visible:
            result[ticker] = [row for _, row in visible]
            if summaries is not None:
                summaries[ticker] = position_summary(visible)
    return result


def position_summary(entries):
    lines = []
    for label, kinds in (("Stock", {"stock_buy", "stock_sell"}), ("Calls", {"call_write", "call_buy"})):
        amounts = [row[5] for kind, row in entries if kind in kinds]
        if not amounts:
            continue
        if any(value in (None, "") for value in amounts):
            lines.append(f"{label} net amount: unavailable (missing amount)")
            continue
        net = sum(Decimal(str(value)).quantize(Decimal(".01"), rounding=ROUND_HALF_UP) for value in amounts)
        is_open = net < 0 if label == "Stock" else net > 0
        status = "OPEN" if is_open else "No open flag"
        lines.append(f"{label} net amount: {net:,.2f} USD  |  {status}")
    return lines


def register(app, database_path):
    @app.get("/api/trade-report")
    def trade_report(account: str = "", year: int = 0):
        with closing(sqlite3.connect(database_path())) as db:
            if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='trading_transactions'").fetchone():
                return {"periods": [], "groups": {}}
            periods = db.execute("SELECT DISTINCT account, substr(trade_date,1,4) FROM trading_transactions ORDER BY account, 2 DESC").fetchall()
            summaries = {}
            groups = trade_rows(db, account, year, summaries) if account and 0 <= year <= 9998 else {}
            return {"periods": periods, "groups": groups, "summaries": summaries}

    @app.get("/api/trade-report/pdf")
    def trade_pdf(account: str, year: int, download: bool = False):
        report = trade_report(account, year)
        if not report["groups"]:
            raise HTTPException(404, "No trades for this account and year.")
        disposition = "attachment" if download else "inline"
        filename = f"RHTC_Trade_Report_{year or 'All'}_{account}.pdf"
        return Response(build_report(account, year or "All years", report["groups"], report["summaries"]), media_type="application/pdf",
                        headers={"Content-Disposition": f'{disposition}; filename="{filename}"',
                                 "Cache-Control": "private, no-store"})

    @app.get("/trading-import", response_class=HTMLResponse)
    def trading_import_page():
        return PAGE

    def transaction_count(db):
        exists = db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='trading_transactions'").fetchone()
        return db.execute("SELECT COUNT(*) FROM trading_transactions").fetchone()[0] if exists else 0

    @app.get("/api/trading-import/count")
    def count_history():
        with closing(sqlite3.connect(database_path(), timeout=20)) as db:
            return {"count": transaction_count(db)}

    @app.delete("/api/trading-import")
    def purge_history(request: Request, expected_count: int):
        if request.headers.get("X-RHTC-Confirm") != "purge-trading-history":
            raise HTTPException(400, "Confirm the purge first.")
        with closing(sqlite3.connect(database_path(), timeout=20)) as db, db:
            db.execute("BEGIN IMMEDIATE")
            count = transaction_count(db)
            if count != expected_count:
                raise HTTPException(409, "Trading history changed. Review the count and confirm again.")
            if count:
                db.execute("DELETE FROM trading_transactions")
            return {"deleted": count}

    @app.post("/api/trading-import")
    async def trading_import(request: Request, account: str, broker: str = "Fidelity"):
        if request.headers.get("content-type", "").split(";")[0] != "text/csv":
            raise HTTPException(415, "Select a CSV file.")
        account = account.strip().upper()
        if broker != "Fidelity IRA" and not re.fullmatch(r"[A-Z0-9_-]{1,40}", account):
            raise HTTPException(422, "Enter a consistent account ID using letters, digits, underscores or hyphens.")
        payload = bytearray()
        async for chunk in request.stream():
            if len(payload) + len(chunk) > LIMIT:
                raise HTTPException(413, "Choose a CSV under 8 MB.")
            payload.extend(chunk)
        try:
            return await run_in_threadpool(import_history, database_path(), account, payload, broker)
        except (ValueError, csv.Error) as exc:
            raise HTTPException(422, str(exc)) from None


PAGE = """<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Import trading history</title><style>body{color-scheme:dark;background:#11171c;color:#edf1f4;font:16px system-ui;margin:auto;max-width:36rem;padding:2rem 1rem}label,input{display:block;margin:1rem 0}input,button{padding:.65rem;max-width:95%;font:inherit}a{color:#e2c778}button{background:#e2c778;color:#141414;border:0;border-radius:.4rem}</style>
<a href="/options/">Back to dashboard</a><h1>Import trading history</h1><p>Select the broker that produced your account history CSV. Use the same account ID for future imports.</p>
<form><label>File format<select id="broker" style="display:block;padding:.65rem;font:inherit"><option>Fidelity</option><option>Fidelity IRA</option><option>Schwab</option><option>Vanguard</option></select></label><p id="format-help" aria-live="polite"></p><label>History CSV<input id="file" type="file" accept=".csv,text/csv" required></label><label>Account ID<input id="account" required maxlength="40" pattern="[A-Za-z0-9_\\-]+" autocomplete="off"></label><button>Import transactions</button></form><hr><button type="button" id="purge" style="background:#a32c32;color:white">Purge all trading history</button><p role="status"></p>
<script>const file=document.querySelector('#file'),account=document.querySelector('#account'),statusText=document.querySelector('[role=status]'),button=document.querySelector('button');
const broker=document.querySelector('#broker');
const guides={'Fidelity IRA':'Fidelity Accounts History CSV. Each transaction is filed under the Account Number in its row, including when the export contains multiple accounts.',Fidelity:'Fidelity account history CSV. Run Date sets the trade date and Amount ($) supplies the cash movement.',Schwab:'Schwab transaction history CSV. Date sets the trade date, Amount supplies the cash movement, and Fees & Comm maps to fees.',Vanguard:'Vanguard transaction history CSV. Trade Date sets the trade date, Transaction Type maps to action, Shares maps to quantity, and Net Amount supplies the cash movement.'};
function showFormat(){account.disabled=broker.value==='Fidelity IRA';account.closest('label').hidden=account.disabled;document.querySelector('#format-help').textContent=guides[broker.value];}
broker.onchange=()=>{showFormat();file.value='';account.value='';statusText.textContent='';};showFormat();
file.onchange=()=>{const match=file.files[0]?.name.match(/History_for_Account_([a-z0-9]+)/i);account.value=broker.value==='Fidelity'?(match?.[1]||''):'';statusText.textContent=''};
document.querySelector('form').onsubmit=async event=>{event.preventDefault();button.disabled=true;statusText.textContent='Importing…';try{const response=await fetch('/options/api/trading-import?account='+encodeURIComponent(account.value.trim())+'&broker='+encodeURIComponent(broker.value),{method:'POST',headers:{'Content-Type':'text/csv'},body:file.files[0]});if(response.status===401)throw Error('Sign in again to import.');const result=await response.json();if(!response.ok)throw Error(result.detail||'Import failed.');statusText.textContent=result.added+' added. '+result.skipped+' already loaded.'}catch(error){statusText.textContent=error.message}finally{button.disabled=false}};
const purge = document.getElementById('purge');
purge.onclick = async () => {
  purge.disabled = true;
  button.disabled = true;
  try {
    const endpoint = '/options/api/trading-import';
    const preview = await fetch(endpoint + '/count', {cache:'no-store'});
    if (!preview.ok) throw Error('Unable to read the transaction count. Check your sign-in and try again.');
    const {count} = await preview.json();
    if (!count) { statusText.textContent = 'No imported transactions to purge.'; return; }
    if (!window.confirm('Permanently delete ' + count + ' imported transactions across ALL trading accounts?')) return;
    const response = await fetch(endpoint + '?expected_count=' + count, {
      method:'DELETE', headers:{'X-RHTC-Confirm':'purge-trading-history'}
    });
    const result = await response.json();
    if (!response.ok) throw Error(result.detail || 'Purge failed.');
    statusText.textContent = result.deleted + ' imported transactions deleted.';
  } catch (error) { statusText.textContent = error.message; }
  finally { purge.disabled = false; button.disabled = false; }
};
</script></html>"""
