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
from html import escape

from fastapi import HTTPException, Request
from fastapi.responses import HTMLResponse, Response
from .trade_pdf import build_cash_activity_report, build_report
from .account_policy import import_status, status_label
from .trade_pdf import build_tax_lot_report, build_open_tax_lot_report, weekly_income_rows, weekly_income_totals
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
        target_account = account
        if embedded:
            source_account = row[account_column].strip().upper()
            if not re.fullmatch(r"[A-Z0-9_-]{1,40}", source_account):
                raise ValueError(f"Invalid account number at line {reader.line_num}.")
            if account and account != source_account:
                continue
            target_account = source_account
        row = [row[i].strip() if i is not None else "" for i in positions]
        try:
            trade_date = row[0]
            if broker == "Schwab":
                # Schwab appends "as of MM/DD/YYYY" to some cash activity dates.
                # The leading date is the transaction date used in the report.
                trade_date = re.split(r"\s+as\s+of\s+", trade_date, maxsplit=1, flags=re.I)[0].strip()
            row[0] = datetime.strptime(trade_date, "%m/%d/%Y").date().isoformat()
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
        if broker == "Fidelity IRA":
            key = "ira:" + key
        counts[target_account, key] += 1
        records.append((target_account, key, counts[target_account, key], *row, broker))
    if not records:
        raise ValueError("No transactions found for the selected account." if embedded and account else "No transactions found.")
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
        if embedded:
            db.execute("""UPDATE trading_transactions SET fingerprint='ira:' || fingerprint
                          WHERE broker='Fidelity IRA' AND length(fingerprint)=64""")
        before_insert = db.total_changes
        db.executemany(f"INSERT INTO trading_transactions(account,fingerprint,occurrence,{COLUMNS},broker) VALUES ({','.join(['?']*17)}) ON CONFLICT(account,fingerprint,occurrence) DO NOTHING", records)
        inserted = db.total_changes - before_insert
        return {"added": inserted, "skipped": len(records) - inserted}


def trade_kind(action, symbol, description):
    option = re.search(r"\d{6}([CP])\d", symbol or "", re.I)
    words = f"{action} {description or ''}"
    call = option[1].upper() == "C" if option else bool(re.search(r"\bCALL\b", words, re.I))
    bought = re.search(r"\b(buy|bought|purchase|purchased)\b", action, re.I)
    sold = re.search(r"\b(sell|sold|sale)\b", action, re.I)
    if call and bought:
        return "call_buy"
    if call and sold and re.search(r"\b(close|closing)\b", action, re.I):
        return "call_sell"
    if call and sold and re.search(r"\b(open|opening)\b", action, re.I):
        return "call_write"
    if not call and not option and not re.search(r"\b(call|put)\b", description or "", re.I):
        if bought or re.search(r"\breinvest\w*", action, re.I):
            return "stock_buy"
        if sold:
            return "stock_sell"


CASH_ACTIVITY_TYPES = (
    "Deposits", "Withdrawals", "Normal distributions", "Transfers in", "Transfers out",
    "Federal taxes withheld or paid", "Dividends", "Interest earned", "Margin interest",
    "Interest", "Bill payments", "Cash advances", "Fees", "Other activity",
)


def cash_activity_type(action, symbol, description, amount):
    action = (action or "").upper()
    description = (description or "").upper()
    if (trade_kind(action, symbol, description)
            or re.search(r"\b(BUY|BOUGHT|SELL|SOLD|PURCHASE|PURCHASED|SALE|REINVEST\w*|ASSIGN\w*|EXERCIS\w*|EXPIR\w*|SPLIT|MERGER|SPIN.?OFF|SYMBOL CHANGE|SECURITIES? (?:RECEIVED|DELIVERED)|SHARES? (?:RECEIVED|DELIVERED))\b", action)):
        return None
    details = f"{action} {description}"
    if re.search(r"\b(FEDERAL|FED|IRS)\b", details) and re.search(r"\b(TAX\w*|WITHH\w*)\b", details):
        return "Federal taxes withheld or paid"
    if re.search(r"\bNORMAL\s+DIST(?:R(?:IBUTIONS?)?)?\b", action):
        return "Normal distributions"
    if re.search(r"\bDIV(?:IDEND)?S?\b", action):
        return "Dividends"
    if re.search(r"\bMARGIN\s+INTEREST\b", action):
        return "Margin interest"
    if re.search(r"\b(INTEREST|INT)\b", action):
        if re.search(r"\bINTEREST\s+(EARNED|CREDITED|RECEIVED)\b", action) or (amount is not None and amount > 0):
            return "Interest earned"
        return "Interest"
    if re.search(r"\bBILL[ -]?PAY(?:MENTS?)?\b", action):
        return "Bill payments"
    if re.search(r"\bCASH[ -]+ADVANCES?\b", action):
        return "Cash advances"
    if re.search(r"\b(FEE|FEES|CHARGE|CHARGES)\b", action):
        return "Fees"
    if re.search(r"\b(TRANSFER\w*|JOURNAL\w*|XFER)\b", action):
        if symbol and not amount:
            return None
        if amount is not None and amount != 0:
            return "Transfers in" if amount > 0 else "Transfers out"
        if re.search(r"\b(IN|RECEIVED|FROM)\b", action):
            return "Transfers in"
        if re.search(r"\b(OUT|SENT|TO)\b", action):
            return "Transfers out"
    if re.search(r"\b(DEPOSIT\w*|CONTRIBUTION\w*|DIRECT CREDIT)\b", action):
        return "Deposits"
    if re.search(r"\b(WITHDRAW\w*|DIRECT DEBIT|CHECK PAID)\b", action):
        return "Withdrawals"
    if re.search(r"\b(ACH|EFT|WIRE)\b", action) and amount:
        return "Deposits" if amount > 0 else "Withdrawals"
    if amount is not None or not symbol:
        return "Other activity"
    return None


def cash_activity_groups(rows):
    groups = {kind: [] for kind in CASH_ACTIVITY_TYPES}
    totals = dict.fromkeys(CASH_ACTIVITY_TYPES, Decimal(0))
    for date, action, symbol, description, raw_amount in rows:
        amount = Decimal(str(raw_amount)) if raw_amount not in (None, "") else None
        kind = cash_activity_type(action, symbol, description, amount)
        if kind is None:
            continue
        groups[kind].append({
            "date": date, "action": action, "symbol": symbol, "description": description,
            "amount": str(amount) if amount is not None else None,
        })
        if amount is not None:
            totals[kind] += amount
    return [{"type": kind, "rows": items, "subtotal": str(totals[kind])}
            for kind, items in groups.items() if items]


def order_same_day(entries):
    def action_order(entry):
        action = entry[1][1] or ""
        if re.search(r"\b(buy|bought|purchase|purchased|reinvest\w*)\b", action, re.I):
            return 0
        if re.search(r"\b(sell|sold|sale)\b", action, re.I):
            return 2
        return 1

    # Python's stable sort preserves the imported order among buys and sells.
    return sorted(entries, key=action_order)


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
        if (re.search(r"\d{6}C\d", symbol or "", re.I) or re.search(r"\bCALL\b", description or "", re.I)) and re.search(r"\b(expired|expiration|assigned|assignment|exercise|exercised)\b", action, re.I):
            kind = "call_end"
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
                summaries[ticker] = position_summary([entry for entry in entries if not year or entry[1][0][:4] <= str(year)])
    return result


def position_summary(entries):
    shares = Decimal(0)
    contracts = Counter()
    seen = set()
    missing = set()
    for kind, row in entries:
        if kind is None:
            continue
        stock = kind.startswith("stock_")
        label = "Stock" if stock else "Calls"
        seen.add(label)
        if row[3] in (None, ""):
            missing.add(label)
            continue
        quantity = abs(Decimal(str(row[3])))
        if stock:
            shares += quantity if kind == "stock_buy" else -quantity
        else:
            series = (row[2] or "").strip().upper()
            if kind == "call_end":
                balance = contracts[series]
                closed = min(abs(balance), quantity)
                contracts[series] += closed if balance < 0 else -closed
            else:
                contracts[series] += quantity if kind == "call_buy" else -quantity

    lines = []
    for label, balance, unit in (("Stock", shares, "shares"), ("Calls", sum(map(abs, contracts.values())), "contracts")):
        if label not in seen:
            continue
        if label in missing:
            lines.append(f"{label}: unknown (missing quantity)")
        else:
            status = "OPEN" if balance else "CLOSED"
            lines.append(f"{label}: {balance:,f} {unit} | {status}")
    return lines


def tax_lot_ticker(symbol):
    """Return the underlying ticker for a share symbol or OCC option symbol."""
    value = (symbol or "").strip().upper().lstrip("-")
    contract = re.match(r"^([A-Z][A-Z0-9.\-]*)\s*\d{6}[CP]\d", value)
    return contract.group(1) if contract else re.split(r"\s+", value, maxsplit=1)[0]


def tax_lot_rows(db, account, year, open_only=False):
    """Match completed security lots FIFO and return Form 8949 columns."""
    rows = db.execute("""
        SELECT trade_date, action, symbol, description, quantity, amount, fingerprint, occurrence
        FROM trading_transactions WHERE account=?
        ORDER BY trade_date, rowid
    """, (account,))
    inventory = {}
    completed = []
    for day, action, symbol, description, quantity, amount, fingerprint, occurrence in rows:
        if open_only and year and day[:4] > str(year):
            break
        if not symbol or quantity in (None, ""):
            continue
        is_option = bool(re.search(r"\d{6}[CP]\d", f"{symbol} {description or ''}", re.I)
                         or re.search(r"\b(call|put)\b", description or "", re.I))
        security = symbol.strip().upper()
        is_call = bool(re.search(r"\d{6}C\d", f"{security} {description or ''}", re.I)
                       or re.search(r"\bcall\b", description or "", re.I))
        expired = bool(re.search(r"\b(expired|expiration)\b", action or "", re.I))
        assigned_call = bool(open_only and is_call and re.search(r"\b(assigned|assignment)\b", action or "", re.I))
        if not (expired or assigned_call) and not re.search(r"\b(buy|bought|sell|sold|sale|purchase|purchased|reinvest\w*)\b", action or "", re.I):
            continue
        try:
            qty = abs(Decimal(str(quantity)))
            cash = abs(Decimal(str(amount))) if amount not in (None, "") else None
        except InvalidOperation:
            continue
        if qty <= 0:
            continue
        bought = bool(re.search(r"\b(buy|bought|purchase|purchased|reinvest\w*)\b", action or "", re.I))
        lots = inventory.setdefault(security, [])
        if expired or assigned_call:
            remaining = qty
            for lot in list(lots):
                if assigned_call and lot["side"] != "short":
                    continue
                matched = min(remaining, lot["qty"])
                if matched <= 0:
                    continue
                if lot["side"] == "long":
                    basis = lot["value"] * matched / lot["qty"] if lot["value"] is not None else None
                    proceeds = Decimal(0)
                else:
                    proceeds = lot["value"] * matched / lot["qty"] if lot["value"] is not None else None
                    basis = Decimal(0)
                if not open_only and not assigned_call and (not year or day[:4] == str(year)):
                    completed.append({"description": f"{matched.normalize():f} {'contract' if lot['option'] else 'share'}{'s' if matched != 1 else ''} {security}",
                                      "ticker": tax_lot_ticker(security), "is_option": lot["option"] or security.startswith("-"), "acquired": lot["date"], "sold": day,
                                      "proceeds": str(proceeds.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)) if proceeds is not None else None,
                                      "basis": str(basis.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)) if basis is not None else None,
                                      "code": "", "adjustment": "",
                                      "gain": str((proceeds - basis).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)) if proceeds is not None and basis is not None else None,
                                      "term": holding_term(lot["date"], day)})
                lot["qty"] -= matched
                if lot["value"] is not None:
                    lot["value"] -= basis if lot["side"] == "long" else proceeds
                remaining -= matched
                if lot["qty"] == 0:
                    lots.remove(lot)
                if remaining == 0:
                    break
            continue
        remaining = qty
        close_side = "short" if bought else "long"
        while remaining > 0 and any(lot["side"] == close_side for lot in lots):
            lot = next(lot for lot in lots if lot["side"] == close_side)
            matched = min(remaining, lot["qty"])
            lot_value = lot["value"] * matched / lot["qty"] if lot["value"] is not None else None
            cash_piece = cash * matched / qty if cash is not None else None
            basis, proceeds = (lot_value, cash_piece) if lot["side"] == "long" else (cash_piece, lot_value)
            if not open_only and (not year or day[:4] == str(year)):
                completed.append({
                    "description": f"{matched.normalize():f} {'contract' if lot['option'] else 'share'}{'s' if matched != 1 else ''} {security}",
                    "ticker": tax_lot_ticker(security), "is_option": lot["option"] or security.startswith("-"), "acquired": lot["date"], "sold": day,
                    "proceeds": str(proceeds.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)) if proceeds is not None else None,
                    "basis": str(basis.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)) if basis is not None else None,
                    "code": "", "adjustment": "",
                    "gain": str((proceeds - basis).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)) if proceeds is not None and basis is not None else None,
                    "term": holding_term(lot["date"], day),
                })
            lot["qty"] -= matched
            if lot["value"] is not None:
                lot["value"] -= lot_value
            remaining -= matched
            if lot["qty"] == 0:
                lots.remove(lot)
        if remaining > 0:
            opened_cash = cash * remaining / qty if cash is not None else None
            lots.append({"date": day, "qty": remaining, "value": opened_cash,
                         "side": "long" if bought else "short", "option": is_option, "call": is_call,
                         "source": (fingerprint, occurrence), "original_qty": qty})
    if open_only:
        as_of = f"{year}-12-31" if year else (day if 'day' in locals() else "")
        as_of_date = datetime.strptime(as_of, "%Y-%m-%d").date() if as_of else None
        grouped = {}
        for security, open_lots in inventory.items():
            ticker = tax_lot_ticker(security)
            if ticker == "FCASH":
                continue
            for lot in open_lots:
                # Calls whose OCC expiration date has passed are no longer open
                # positions, even when the broker omits a separate expiry row.
                expiration = re.search(r"(\\d{6})C\\d", security)
                if lot.get("call") and expiration and as_of_date:
                    try:
                        expiration_date = datetime.strptime("20" + expiration.group(1), "%Y%m%d").date()
                    except ValueError:
                        expiration_date = None
                    if expiration_date and expiration_date <= as_of_date:
                        continue
                # Keep different option contracts separate, but consolidate
                # same-security lots acquired on the same date.
                key = (ticker, lot["date"], security, lot["side"], lot["option"])
                group = grouped.setdefault(key, {"quantity": Decimal(0), "amount": Decimal(0), "known": True, "sources": [], "deletable": True})
                group["quantity"] += lot["qty"]
                group["sources"].append(lot["source"])
                group["deletable"] = group["deletable"] and lot["qty"] == lot["original_qty"]
                if lot["value"] is None:
                    group["known"] = False
                elif group["known"]:
                    group["amount"] += lot["value"]
        result = []
        for (ticker, acquired, security, side, is_option), group in grouped.items():
            qty = group["quantity"]
            value = group["amount"] if group["known"] else None
            display_value = -value if value is not None and not is_option and side == "long" else value
            amount_value = str(display_value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)) if display_value is not None else None
            unit_value = str((display_value / (qty * 100 if is_option else qty)).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)) if display_value is not None and qty else None
            result.append({"description": f"{format(qty.normalize(), ',f')} {'contract' if is_option else 'share'}{'s' if qty != 1 else ''} {security}",
                           "ticker": ticker, "side": side, "acquired": acquired,
                           "quantity": format(qty.normalize(), "f"), "amount": amount_value,
                           "unit_amount": unit_value, "amount_type": "Premium" if is_option else ("Cost" if side == "long" else "Proceeds"),
                           "term": holding_term(acquired, as_of) if as_of else "short",
                           "delete_id": hashlib.sha256(json.dumps(sorted(group["sources"])).encode()).hexdigest() ,
                           "_sources": group["sources"] })
        def open_lot_sort_key(row):
            description = row["description"]
            if " share" in description:
                return (row["ticker"], 0, row["acquired"], 0, Decimal(0), description)
            contract = re.search(r"(\\d{6})([CP])(\\d+(?:\\.\\d+)?)", description)
            if contract:
                return (row["ticker"], 1, contract.group(1), 0 if contract.group(2) == "C" else 1,
                        Decimal(contract.group(3)), description)
            return (row["ticker"], 1, "999999", 9, Decimal(0), description)
        return sorted(result, key=open_lot_sort_key)
    return sorted(completed, key=lambda row: (row["sold"], row["description"], row["acquired"]))


def holding_term(acquired, sold):
    """Classify a lot as long-term only after it has been held over one year."""
    acquired_date = datetime.strptime(acquired, "%Y-%m-%d").date()
    sold_date = datetime.strptime(sold, "%Y-%m-%d").date()
    try:
        one_year = acquired_date.replace(year=acquired_date.year + 1)
    except ValueError:  # February 29 acquisition in a non-leap year.
        one_year = acquired_date.replace(year=acquired_date.year + 1, day=28)
    return "long" if sold_date > one_year else "short"


def tax_lot_summary(lots):
    totals = {term: {"proceeds": Decimal(0), "basis": Decimal(0), "gain": Decimal(0), "count": 0}
              for term in ("short", "long")}
    for lot in lots:
        if lot.get("gain") in (None, ""):
            continue
        total = totals[lot["term"]]
        total["proceeds"] += Decimal(lot["proceeds"])
        total["basis"] += Decimal(lot["basis"])
        total["gain"] += Decimal(lot["gain"])
        total["count"] += 1
    return {term: {key: str(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)) if key != "count" else value
                   for key, value in values.items()} for term, values in totals.items()}


def register(app, database_path):
    def report_status(db, account):
        if not account:
            return import_status(None)
        columns = {col[1] for col in db.execute("PRAGMA table_info(trading_transactions)")}
        if not columns:
            return import_status(None)
        broker_col = "broker" if "broker" in columns else "\'Fidelity\'"
        statuses = {status_label(import_status(row[0])) for row in db.execute(f"SELECT DISTINCT {broker_col} FROM trading_transactions WHERE account=?", (account,))}
        if len(statuses) == 1:
            tax, funding = next(iter(statuses)).split(" / ")
            return {"tax_status": tax, "funding_status": funding}
        return import_status(None)

    @app.get("/api/trade-report")
    def trade_report(account: str = "", year: int = 0):
        with closing(sqlite3.connect(database_path())) as db:
            if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='trading_transactions'").fetchone():
                return {"periods": [], "groups": {}}
            periods = db.execute("SELECT DISTINCT account, substr(trade_date,1,4) FROM trading_transactions ORDER BY account, 2 DESC").fetchall()
            summaries = {}
            groups = trade_rows(db, account, year, summaries) if account and 0 <= year <= 9998 else {}
            return {"periods": periods, "groups": groups, "summaries": summaries, "account_status": report_status(db, account)}

    @app.get("/api/trade-report/pdf")
    def trade_pdf(account: str, year: int, download: bool = False, title: str = ""):
        report = trade_report(account, year)
        if not report["groups"]:
            raise HTTPException(404, "No trades for this account and year.")
        disposition = "attachment" if download else "inline"
        filename = f"RHTC_Trade_Report_{year or 'All'}_{account}.pdf"
        return Response(build_report(account, year or "All years", report["groups"], report["summaries"], title=title, account_classification=status_label(report["account_status"])), media_type="application/pdf",
                        headers={"Content-Disposition": f'{disposition}; filename="{filename}"',
                                 "Cache-Control": "private, no-store"})

    @app.get("/api/tax-lot-report")
    def tax_lot_report(account: str = "", year: int = 0, ticker: str = "", weekly_income: bool = False, weekly_detail: bool = False, metadata_only: bool = False):
        with closing(sqlite3.connect(database_path())) as db:
            if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='trading_transactions'").fetchone():
                return {"periods": [], "lots": [], "tickers": [], "summary": tax_lot_summary([])}
            periods = db.execute("SELECT DISTINCT account, substr(trade_date,1,4) FROM trading_transactions ORDER BY account, 2 DESC").fetchall()
            symbols = db.execute("SELECT DISTINCT symbol FROM trading_transactions WHERE account=? AND COALESCE(TRIM(symbol),'')<>''", (account,)).fetchall() if account else []
            tickers = sorted({value for (symbol,) in symbols if (value := tax_lot_ticker(symbol)) and re.fullmatch(r"[A-Z0-9./-]{1,16}", value)})
            if metadata_only:
                return {"periods": periods, "tickers": tickers}
            lots = tax_lot_rows(db, account, year) if account and 0 <= year <= 9998 else []
            ticker = ticker.strip().upper()
            if ticker:
                if not re.fullmatch(r"[A-Z0-9.\-]{1,16}", ticker):
                    raise HTTPException(422, "Enter a valid ticker symbol.")
                lots = [lot for lot in lots if lot.get("ticker", "").upper() == ticker]
            if weekly_income and account:
                if not 1 <= year <= 9998:
                    raise HTTPException(422, "Select a tax year for the weekly report.")
                weeks = weekly_income_rows(lots, year, include_details=weekly_detail)
                return {"periods": periods, "weeks": weeks, "totals": weekly_income_totals(weeks), "account_status": report_status(db, account)}
            return {"periods": periods, "lots": lots, "tickers": tickers, "summary": tax_lot_summary(lots), "account_status": report_status(db, account)}

    @app.get("/api/tax-lot-report/pdf")
    def tax_lot_pdf(account: str, year: int, ticker: str = "", weekly_income: bool = False, download: bool = False, weekly_detail: bool = False, title: str = ""):
        if weekly_income and not 1 <= year <= 9998:
            raise HTTPException(422, "Select a tax year for the weekly report.")
        report = tax_lot_report(account, year, ticker)
        if not report["lots"]:
            raise HTTPException(404, "No completed tax lots for this account, ticker, and tax year.")
        disposition = "attachment" if download else "inline"
        ticker = ticker.strip().upper()
        if weekly_income:
            filename = f"RHTC_Weekly_Income_{'Detail' if weekly_detail else 'Summary'}_Report_{year or 'All'}_{account}.pdf"
        else:
            ticker_suffix = f"_{ticker}" if ticker else ""
            filename = f"RHTC_Form_8949_{year or 'All'}{ticker_suffix}_{account}.pdf"
        return Response(build_tax_lot_report(account, year or "All years", report["lots"], ticker=ticker, weekly_income=weekly_income, weekly_detail=weekly_detail, title=title, account_classification=status_label(report["account_status"])), media_type="application/pdf",
                        headers={"Content-Disposition": f'{disposition}; filename="{filename}"',
                                 "Cache-Control": "private, no-store"})

    @app.get("/api/open-tax-lot-report")
    def open_tax_lot_report(account: str = "", year: int = 0):
        with closing(sqlite3.connect(database_path())) as db:
            if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='trading_transactions'").fetchone():
                return {"periods": [], "lots": []}
            bounds = db.execute("SELECT account, MIN(substr(trade_date,1,4)), MAX(substr(trade_date,1,4)) FROM trading_transactions GROUP BY account ORDER BY account").fetchall()
            periods = [(account_id, str(period_year)) for account_id, first, last in bounds
                       for period_year in range(int(last), int(first) - 1, -1)]
            lots = tax_lot_rows(db, account, year, open_only=True) if account and 0 <= year <= 9998 else []
            return {"periods": periods, "lots": [{k: v for k, v in lot.items() if k != "_sources"} for lot in lots], "account_status": report_status(db, account)}

    @app.post("/api/open-tax-lot-report/delete")
    def delete_open_tax_lots(payload: dict):
        account = payload.get("account")
        ids = payload.get("ids")
        if not isinstance(account, str) or not account or (type(payload.get("year")) is not int or not 0 <= payload["year"] <= 9998) or not isinstance(ids, list) or not ids or len(ids) > 1000 or any(not isinstance(i, str) or not re.fullmatch(r"[a-f0-9]{64}", i) for i in ids):
            raise HTTPException(422, "Select valid open lots from the report.")
        with closing(sqlite3.connect(database_path(), timeout=20)) as db, db:
            db.execute("BEGIN IMMEDIATE")
            lots = {lot["delete_id"]: lot for lot in tax_lot_rows(db, account, payload["year"], open_only=True)}
            if not set(ids).issubset(lots):
                raise HTTPException(409, "Selected lots changed. Refresh the report.")
            sources = {tuple(source) for ident in ids for source in lots[ident]["_sources"]}
            db.executemany("DELETE FROM trading_transactions WHERE account=? AND fingerprint=? AND occurrence=?", [(account, *source) for source in sources])
        return {"deleted_count": len(sources)}

    @app.get("/api/open-tax-lot-report/pdf")
    def open_tax_lot_pdf(account: str, year: int, download: bool = False, title: str = ""):
        report = open_tax_lot_report(account, year)
        if not report["lots"]:
            raise HTTPException(404, "No open tax lots for this account as of the selected year end.")
        disposition = "attachment" if download else "inline"
        filename = f"RHTC_Open_Tax_Lots_{year or 'Latest'}_{account}.pdf"
        return Response(build_open_tax_lot_report(account, year or "Latest available", report["lots"], title=title, account_classification=status_label(report["account_status"])), media_type="application/pdf",
                        headers={"Content-Disposition": f'{disposition}; filename="{filename}"',
                                 "Cache-Control": "private, no-store"})

    @app.get("/api/cash-activity-report")
    def cash_activity_report(broker: str = "", account: str = ""):
        if broker and broker not in FORMATS:
            raise HTTPException(422, "Choose an account type.")
        with closing(sqlite3.connect(database_path(), timeout=20)) as db:
            columns = {column[1] for column in db.execute("PRAGMA table_info(trading_transactions)")}
            if not columns:
                return {"accounts": [], "groups": []}
            broker_column = "broker" if "broker" in columns else "'Fidelity'"
            accounts = db.execute(
                f"SELECT DISTINCT {broker_column}, account FROM trading_transactions ORDER BY 1, 2"
            ).fetchall()
            groups = []
            if broker and account:
                rows = db.execute(
                    "SELECT trade_date, action, symbol, description, amount FROM trading_transactions "
                    f"WHERE {broker_column}=? AND account=? ORDER BY trade_date, rowid",
                    (broker, account),
                )
                groups = cash_activity_groups(rows)
            return {"accounts": accounts, "groups": groups, "account_status": import_status(broker)}

    @app.get("/api/cash-activity-report/pdf")
    def cash_activity_pdf(broker: str, account: str, download: bool = False, title: str = ""):
        groups = cash_activity_report(broker, account)["groups"]
        if not groups:
            raise HTTPException(404, "No cash activity for this account.")
        disposition = "attachment" if download else "inline"
        return Response(build_cash_activity_report(broker, account, groups, title=title, account_classification=status_label(import_status(broker))), media_type="application/pdf",
                        headers={"Content-Disposition": f'{disposition}; filename="RHTC_Cash_Activity_Report.pdf"',
                                 "Cache-Control": "private, no-store"})

    @app.get("/trading-import", response_class=HTMLResponse)
    def trading_import_page(title: str = ""):
        return PAGE.replace("Import CSV files", escape(title.strip()[:300] or "Import CSV files"))

    def transaction_count(db, broker, account):
        if broker not in FORMATS or not re.fullmatch(r"[A-Z0-9_-]{1,40}", account):
            raise HTTPException(422, "Choose a file format and enter an account ID.")
        exists = db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='trading_transactions'").fetchone()
        if not exists:
            return 0
        if "broker" not in {col[1] for col in db.execute("PRAGMA table_info(trading_transactions)")}:
            db.execute("ALTER TABLE trading_transactions ADD COLUMN broker TEXT NOT NULL DEFAULT 'Fidelity'")
        return db.execute("SELECT COUNT(*) FROM trading_transactions WHERE broker=? AND account=?", (broker, account)).fetchone()[0]

    @app.get("/api/trading-import/accounts")
    def list_import_accounts(broker: str):
        if broker not in FORMATS:
            raise HTTPException(422, "Choose a file format.")
        with closing(sqlite3.connect(database_path(), timeout=20)) as db:
            columns = {column[1] for column in db.execute("PRAGMA table_info(trading_transactions)")}
            if "account" not in columns:
                return {"accounts": []}
            if "broker" in columns:
                rows = db.execute(
                    "SELECT DISTINCT account FROM trading_transactions WHERE broker=? ORDER BY account",
                    (broker,),
                )
            elif broker == "Fidelity":
                rows = db.execute("SELECT DISTINCT account FROM trading_transactions ORDER BY account")
            else:
                return {"accounts": []}
            return {"accounts": [account for (account,) in rows if account]}

    @app.get("/api/trading-import/count")
    def count_history(broker: str, account: str):
        with closing(sqlite3.connect(database_path(), timeout=20)) as db:
            return {"count": transaction_count(db, broker, account)}

    @app.delete("/api/trading-import")
    def purge_history(request: Request, expected_count: int, broker: str, account: str):
        if request.headers.get("X-RHTC-Confirm") != "purge-trading-history":
            raise HTTPException(400, "Confirm the purge first.")
        with closing(sqlite3.connect(database_path(), timeout=20)) as db, db:
            db.execute("BEGIN IMMEDIATE")
            count = transaction_count(db, broker, account)
            if count != expected_count:
                raise HTTPException(409, "Trading history changed. Review the count and confirm again.")
            if count:
                db.execute("DELETE FROM trading_transactions WHERE broker=? AND account=?", (broker, account))
            return {"deleted": count}

    @app.post("/api/trading-import")
    async def trading_import(request: Request, account: str, broker: str = "Fidelity"):
        if request.headers.get("content-type", "").split(";")[0] != "text/csv":
            raise HTTPException(415, "Select a CSV file.")
        account = account.strip().upper()
        if (account or broker != "Fidelity IRA") and not re.fullmatch(r"[A-Z0-9_-]{1,40}", account):
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
<title>Import CSV files</title><style>body{color-scheme:dark;background:#11171c;color:#edf1f4;font:16px system-ui;margin:auto;max-width:36rem;padding:2rem 1rem}label,input{display:block;margin:1rem 0}input,button{padding:.65rem;max-width:95%;font:inherit}a{color:#e2c778}button{background:#e2c778;color:#141414;border:0;border-radius:.4rem}</style>
<a href="/options/">Back to dashboard</a><h1>Import CSV files</h1><p>Select the broker that produced your account history CSV. Use the same account ID for future imports.</p>
<form><label>File format<select id="broker" style="display:block;padding:.65rem;font:inherit"><option>Fidelity</option><option>Fidelity IRA</option><option>Schwab</option><option>Vanguard</option></select></label><p id="format-help" aria-live="polite"></p><label>History CSV<input id="file" type="file" accept=".csv,text/csv" required></label><label for="saved-account">Existing account</label><select id="saved-account" style="padding:.65rem;font:inherit;max-width:100%"><option value="">Select an account</option></select><label>Account ID<input id="account" required maxlength="40" pattern="[A-Za-z0-9_\\-]+" autocomplete="off"></label><button>Import transactions</button></form><hr><button type="button" id="purge" style="background:#a32c32;color:white">Purge selected account</button><p role="status"></p>
<script>const file=document.querySelector('#file'),account=document.querySelector('#account'),statusText=document.querySelector('[role=status]'),button=document.querySelector('button');
const broker=document.querySelector('#broker'),savedAccount=document.querySelector('#saved-account');
const guides={'Fidelity IRA':'Fidelity Accounts History CSV. Leave Account ID blank to use the account numbers in the CSV, or enter an account number to import only its matching rows.',Fidelity:'Fidelity account history CSV. Run Date sets the trade date and Amount ($) supplies the cash movement.',Schwab:'Schwab transaction history CSV. Date sets the trade date, Amount supplies the cash movement, and Fees & Comm maps to fees.',Vanguard:'Vanguard transaction history CSV. Trade Date sets the trade date, Transaction Type maps to action, Shares maps to quantity, and Net Amount supplies the cash movement.'};
function showFormat(){account.required=broker.value!=='Fidelity IRA';account.placeholder=account.required?'Enter an account ID':'Optional for Fidelity IRA';document.querySelector('#format-help').textContent=guides[broker.value];}
let accountsRequest=0;
function syncAccountSelection(){savedAccount.value=account.value.trim().toUpperCase();if(!savedAccount.value)savedAccount.selectedIndex=0;}
async function loadAccounts(){
  const request=++accountsRequest;
  savedAccount.replaceChildren(new Option('Loading accounts…',''));
  savedAccount.disabled=true;
  try{
    const response=await fetch('/options/api/trading-import/accounts?'+new URLSearchParams({broker:broker.value}),{cache:'no-store'});
    if(!response.ok)throw Error('Could not load accounts');
    const {accounts}=await response.json();
    if(request!==accountsRequest)return;
    savedAccount.replaceChildren(new Option(accounts.length?'Select an account':'No saved accounts',''),...accounts.map(id=>new Option(id,id)));
    savedAccount.disabled=!accounts.length;
    syncAccountSelection();
  }catch{
    if(request===accountsRequest)savedAccount.replaceChildren(new Option('Saved accounts unavailable',''));
  }
}
savedAccount.onchange=()=>{account.value=savedAccount.value;statusText.textContent='';};
account.oninput=()=>{syncAccountSelection();statusText.textContent='';};
broker.onchange=()=>{showFormat();file.value='';account.value='';statusText.textContent='';loadAccounts();};
showFormat();loadAccounts();
file.onchange=()=>{
  const match=file.files[0]?.name.match(/History_for_Account_([a-z0-9]+)/i);
  if(broker.value==='Fidelity'&&!account.value.trim()&&match)account.value=match[1];
  syncAccountSelection();
  statusText.textContent='';
};
document.querySelector('form').onsubmit=async event=>{event.preventDefault();button.disabled=true;statusText.textContent='Importing…';try{const response=await fetch('/options/api/trading-import?account='+encodeURIComponent(account.value.trim())+'&broker='+encodeURIComponent(broker.value),{method:'POST',headers:{'Content-Type':'text/csv'},body:file.files[0]});if(response.status===401)throw Error('Sign in again to import.');const result=await response.json();if(!response.ok)throw Error(result.detail||'Import failed.');statusText.textContent=result.added+' added. '+result.skipped+' already loaded.';loadAccounts()}catch(error){statusText.textContent=error.message}finally{button.disabled=false}};
const purge = document.getElementById('purge');
purge.onclick = async () => {
  purge.disabled = true;
  button.disabled = true;
  try {
    const endpoint = '/options/api/trading-import';
    const id = account.value.trim().toUpperCase();
    const format = broker.value;
    if (!id) throw Error('Select or enter the account ID to purge.');
    const scope = new URLSearchParams({broker:format, account:id});
    const preview = await fetch(endpoint + '/count?' + scope, {cache:'no-store'});
    if (!preview.ok) throw Error('Unable to read the transaction count. Check your sign-in and try again.');
    const {count} = await preview.json();
    if (!count) { statusText.textContent = 'No imported transactions to purge.'; return; }
    if (!window.confirm('Permanently delete ' + count + ' transactions for ' + format + ' account ' + id + '?')) return;
    const response = await fetch(endpoint + '?' + scope + '&expected_count=' + count, {
      method:'DELETE', headers:{'X-RHTC-Confirm':'purge-trading-history'}
    });
    const result = await response.json();
    if (!response.ok) throw Error(result.detail || 'Purge failed.');
    statusText.textContent = result.deleted + ' imported transactions deleted.';
    loadAccounts();
  } catch (error) { statusText.textContent = error.message; }
  finally { purge.disabled = false; button.disabled = false; }
};
</script></html>"""
