import sqlite3
import unittest
from fastapi import HTTPException
from app.options.trading_import import tax_lot_rows
from app.options.open_lot_safeguards import guarded_open_lots, delete_guarded_lots
from app.options.trade_pdf import weekly_income_rows, weekly_income_totals


class OpenLotSafeguards(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(":memory:")
        self.addCleanup(self.db.close)
        self.db.execute("CREATE TABLE trading_transactions(account TEXT, trade_date TEXT, action TEXT, symbol TEXT, description TEXT, quantity TEXT, amount TEXT, fingerprint TEXT, occurrence INTEGER, UNIQUE(account,fingerprint,occurrence))")
        for account, day, action, symbol, qty, amount, fp in [
            ("A","2025-01-02","Buy","ABC",100,-2000,"purchase"),
            ("A","2025-01-02","Buy","ABC",10,-300,"grouped"),
            ("A","2025-01-09","Sell","ABC",40,1000,"sale"),
            ("A","2025-02-03","Buy","XYZ",10,-100,"unclosed"),
            ("A","2025-12-01","Buy","DEF",20,-200,"later"),
            ("A","2026-02-02","Sell","DEF",20,300,"later-sale"),
            ("A","2026-03-01","Buy","QRS",5,-50,"safe1"),
            ("A","2026-03-01","Buy","QRS",7,-84,"safe2"),
            ("B","2025-02-03","Buy","XYZ",10,-100,"unclosed"),
        ]:
            self.db.execute("INSERT INTO trading_transactions VALUES (?,?,?,?,?,?,?,?,?)",(account,day,action,symbol,"",str(qty),str(amount),fp,0))
        self.db.commit()

    def row(self,ticker,account="A",year=0):
        return next(r for r in guarded_open_lots(self.db,account,year,tax_lot_rows) if r["ticker"]==ticker)

    def delete(self,ids,account="A",year=0):
        with self.db:
            self.db.execute("BEGIN IMMEDIATE")
            return delete_guarded_lots(self.db,account,year,ids,tax_lot_rows)

    def reject(self,ids,account="A",year=0):
        before=self.db.execute("SELECT * FROM trading_transactions ORDER BY rowid").fetchall()
        with self.assertRaises(HTTPException) as ctx:
            self.delete(ids,account,year)
        self.assertEqual(ctx.exception.status_code,409)
        self.assertEqual(before,self.db.execute("SELECT * FROM trading_transactions ORDER BY rowid").fetchall())

    def test_partial_group(self):
        row=self.row("ABC")
        self.assertFalse(row["deletable"])
        self.assertEqual(row["quantity"],"70")
        self.reject([row["delete_id"]])

    def test_mixed_atomic(self):
        self.reject([self.row("ABC")["delete_id"],self.row("QRS")["delete_id"]])

    def test_historical(self):
        for symbol in ("DEF","XYZ"):
            row=self.row(symbol,year=2025)
            self.assertFalse(row["deletable"])
            self.reject([row["delete_id"]],year=2025)

    def test_account_isolation(self):
        a=self.row("XYZ")
        b=self.row("XYZ",account="B")
        self.assertNotEqual(a["delete_id"],b["delete_id"])
        self.reject([a["delete_id"]],account="B")
        self.assertEqual(self.delete([a["delete_id"]]),1)
        self.assertEqual(self.row("XYZ",account="B")["quantity"],"10")

    def test_reports_unchanged(self):
        def snapshot():
            return (tax_lot_rows(self.db,"A",0),[
                (rows,weekly_income_totals(rows))
                for y in (2025,2026) for g in ("weekly","monthly","quarterly")
                for rows in [weekly_income_rows(tax_lot_rows(self.db,"A",y),y,include_details=True,grouping=g,drill_down=True)]])
        before=snapshot()
        row=self.row("QRS",year=2026)
        self.assertTrue(row["deletable"])
        self.assertEqual(self.delete([row["delete_id"]],year=2026),2)
        self.assertEqual(snapshot(),before)

    def test_stale(self):
        row=self.row("QRS")
        self.db.execute("INSERT INTO trading_transactions VALUES ('A','2026-04-01','Sell','QRS','','1','20','new-sale',0)")
        self.db.commit()
        self.reject([row["delete_id"]])

    def test_partial_option(self):
        self.db.executemany("INSERT INTO trading_transactions VALUES (?,?,?,?,?,?,?,?,?)",[
            ("A","2026-03-01","Sell","-OPT261218C100","Call","3","300","option-open",0),
            ("A","2026-03-02","Buy","-OPT261218C100","Call","1","50","option-close",0)])
        self.db.commit()
        row=self.row("OPT")
        self.assertFalse(row["deletable"])
        self.reject([row["delete_id"]])
