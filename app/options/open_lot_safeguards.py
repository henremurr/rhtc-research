"""Safeguards for open-lot deletion."""
import hashlib
import json
from fastapi import HTTPException


def deletion_id(account, sources):
    return hashlib.sha256(json.dumps([account, sorted(sources)]).encode()).hexdigest()


def guarded_open_lots(db, account, year, tax_lot_rows):
    rows = tax_lot_rows(db, account, year, open_only=True)
    latest = db.execute('SELECT MAX(substr(trade_date,1,4)) FROM trading_transactions WHERE account=?', (account,)).fetchone()[0]
    historical = bool(year and latest and year < int(latest))
    current = {r['delete_id']: r for r in tax_lot_rows(db, account, 0, open_only=True)} if year and not historical else {r['delete_id']: r for r in rows}
    for row in rows:
        if historical:
            reason = 'Historical reporting period is read-only.'
        elif not row.get('deletable'):
            reason = 'Original transaction contributed to a completed trade.'
        elif not current.get(row['delete_id'], {}).get('deletable'):
            reason = 'Lot is no longer fully open in the current ledger.'
        else:
            reason = None
        row['deletable'] = reason is None
        row['delete_reason'] = reason
    return rows


def delete_guarded_lots(db, account, year, ids, tax_lot_rows):
    """Caller holds BEGIN IMMEDIATE; failures roll back the entire transaction."""
    lots = {r['delete_id']: r for r in guarded_open_lots(db, account, year, tax_lot_rows)}
    if not set(ids).issubset(lots):
        raise HTTPException(409, 'Selected lots changed. Refresh the report.')
    if any(not lots[i]['deletable'] for i in ids):
        raise HTTPException(409, 'Selection includes protected or historical lots. No transactions deleted.')
    before = tax_lot_rows(db, account, 0)
    sources = {tuple(s) for i in ids for s in lots[i]['_sources']}
    db.execute('SAVEPOINT guarded_lot_delete')
    try:
        for source in sources:
            cursor = db.execute('DELETE FROM trading_transactions WHERE account=? AND fingerprint=? AND occurrence=?', (account, *source))
            if cursor.rowcount != 1:
                raise HTTPException(409, 'Source transaction changed. No transactions deleted.')
        if tax_lot_rows(db, account, 0) != before:
            raise HTTPException(409, 'Deletion would change completed trades. No transactions deleted.')
    except BaseException:
        db.execute('ROLLBACK TO guarded_lot_delete')
        db.execute('RELEASE guarded_lot_delete')
        raise
    db.execute('RELEASE guarded_lot_delete')
    return len(sources)
