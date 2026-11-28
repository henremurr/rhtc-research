import unittest
import tempfile
from pathlib import Path
from contextlib import closing
from datetime import timedelta
from unittest.mock import patch
from app.options import kalshi_ingestion as ki,kalshi_metadata_sync as km,kalshi_quote_refresh as kq,prediction_markets as pm
from app.options.kalshi_reconciliation import reconcile

class OptimizationTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        for p in (patch("app.options.api.watchlist_db_path",return_value=Path(tmp.name)/"watch.sqlite3"),patch("app.options.api.read_watchlist",return_value=[])):
            p.start()
            self.addCleanup(p.stop)

    def market(self,ticker="A",status="active"):
        return {"ticker":ticker,"market_type":"binary","status":status,"title":"AI chip","rules_primary":"Rules","updated_time":(ki.now()-timedelta(minutes=3)).isoformat(),"yes_bid_dollars":".6","yes_ask_dollars":".8","yes_bid_size_fp":"10","yes_ask_size_fp":"10"}

    def seed(self):
        cp=ki.persist(ki.begin(),[self.market()],None)
        ki.finish(cp)
        cp=pm.persist_page(pm.begin_checkpoint(),[{"id":"1","question":"AI chips","active":True,"closed":False,"outcomes":["Yes","No"],"outcomePrices":[".4",".6"]}],None)
        pm.finish_checkpoint(cp)

    def test_combined_catalog(self):
        self.seed()
        result=pm.catalog_page("All","All",0,1,"prob-yes","all")
        self.assertEqual(result[2],2)
        self.assertEqual(result[3][0]["id"],"kalshi:A")
        self.assertEqual(pm.catalog_page("AI/I","All",1,1,"prob-yes","all")[3][0]["id"],"1")
        with closing(ki.connect()) as db,db:
            db.execute("DELETE FROM market_catalog")
        self.assertIsNone(pm.catalog_page("All","All",0,1,"relevance","all"))
        while not ki.backfill_latest_catalog(1):
            pass
        self.assertEqual(pm.catalog_page("All","All",0,1,"relevance","all")[2],2)

    def test_shadow_watermark_and_quotes(self):
        self.seed()
        before=ki.latest()
        with closing(km.connect()) as db,db:
            now=int(ki.now().timestamp())
            db.execute("INSERT INTO metadata_checkpoint VALUES(1,?,?,NULL,0,0)",(now-600,now-120))
            cp=dict(db.execute("SELECT * FROM metadata_checkpoint").fetchone())
        cp=km.persist(cp,[self.market("B")],"next")
        with self.assertRaises(ValueError):
            km.finish(cp)
        with closing(km.connect()) as db:
            self.assertIsNone(db.execute("SELECT * FROM metadata_watermark").fetchone())
        cp=km.persist(cp,[self.market("A","closed")],None)
        self.assertEqual(km.finish(cp),2)
        self.assertEqual(kq.persist(["kalshi:A"],[self.market("A","closed")]),1)
        self.assertEqual(ki.latest(),before)
        result=reconcile()
        self.assertEqual(result["metadata_comparison"]["active_absent"],1)
        self.assertEqual(result["metadata_comparison"]["inactive_present"],1)
        with self.assertRaises(ValueError):
            kq.persist(["kalshi:A"],[self.market("B")])
