"""RHTC account policy; classifications are not verified balances or tax advice."""

ACCOUNT_TYPES = ("Fidelity Brokerage", "Fidelity IRA", "Schwab PRCA", "Vanguard 401k", "Vanguard IRA-M")
ANALYSIS_POLICY = "Account policy: Fidelity Brokerage is taxable and margin-enabled; retirement accounts are non-taxable for current in-account trading and cash-only. Retirement distributions may be taxable. Never infer actual margin borrowing from margin eligibility. Apply margin costs and maintenance risk only to Fidelity Brokerage; cash accounts require available cash. Consider realized gains/losses, holding periods, option taxation and cross-account wash-sale risk, including IRA purchases. Do not treat retirement assets as freely transferable collateral. Distinguish gross trading performance from taxable income; do not estimate taxes without sufficient data. Unassigned holdings have unknown account status."


def account_status(account):
    if account == "Fidelity Brokerage":
        return {"tax_status": "Taxable", "funding_status": "Margin"}
    if account in ACCOUNT_TYPES:
        return {"tax_status": "Non-taxable", "funding_status": "Cash"}
    return {"tax_status": "Unknown", "funding_status": "Unknown"}


def import_status(broker):
    return account_status({"Fidelity": "Fidelity Brokerage", "Fidelity IRA": "Fidelity IRA", "Schwab": "Schwab PRCA", "Vanguard": "Vanguard 401k"}.get(broker))


def status_label(status):
    return f"{status['tax_status']} / {status['funding_status']}"
