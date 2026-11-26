from app.options.account_policy import ACCOUNT_TYPES, account_status, import_status


def test_account_classifications():
    for account in ACCOUNT_TYPES:
        expected = {"tax_status": "Taxable", "funding_status": "Margin"} if account == "Fidelity Brokerage" else {"tax_status": "Non-taxable", "funding_status": "Cash"}
        assert account_status(account) == expected
    assert account_status(None) == {"tax_status": "Unknown", "funding_status": "Unknown"}


def test_import_classifications():
    assert import_status("Fidelity") == account_status("Fidelity Brokerage")
    for broker in ("Fidelity IRA", "Schwab", "Vanguard"):
        assert import_status(broker) == account_status("Fidelity IRA")
