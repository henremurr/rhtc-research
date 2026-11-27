import asyncio
import unittest
import httpx
from app.options.prediction_markets import discover, normalize

class PredictionMarketTests(unittest.TestCase):
    def test_normalization(self):
        row = normalize({"id": "1", "question": "Nuclear power for AI data centers",
                         "outcomes": '["Yes","No"]', "outcomePrices": '["0.7","0.3"]'})
        self.assertEqual(row["probabilities"]["Yes"], .7)
        self.assertIn("AI/I", row["topics"])
        self.assertIn("EFM/I", row["topics"])
        self.assertEqual(row["quality"], "limited")

    def test_all_pages_and_unclassified(self):
        async def run():
            def handler(request):
                cursor = request.url.params.get("after_cursor")
                self.assertEqual(request.url.params["active"], "true")
                self.assertEqual(request.url.params["closed"], "false")
                self.assertNotIn("offset", request.url.params)
                if cursor is None:
                    return httpx.Response(200,json={"markets":[{"id":"1","question":"Unfamiliar subject","active":True,"closed":False}],"next_cursor":"next"})
                self.assertEqual(cursor,"next")
                return httpx.Response(200,json={"markets":[{"id":"2","question":"Unfamiliar subject","active":True,"closed":False}]})
            async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
                rows = await discover(client)
            self.assertEqual(len(rows),2)
            self.assertEqual(rows[0]["topics"],[])
        asyncio.run(run())

    def test_repeated_page_fails(self):
        async def run():
            def handler(request):
                return httpx.Response(200,json={"markets":[{"id":"1","active":True,"closed":False}],"next_cursor":"repeat"})
            async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
                with self.assertRaises(ValueError):
                    await discover(client)
        asyncio.run(run())

    def test_portfolio_mapping_is_account_specific(self):
        from app.options.prediction_markets import map_portfolio, validate_research
        row = normalize({"id":"1","question":"New reactor approval"})
        row["research"] = validate_research({"tickers":["OKLO","NEW"],"topics":["EFM/I"],"relevance":9})
        watchlist = [{"symbol":"OKLO","account":"Cash","quantity":100,"peak":"EFM/I"},
                     {"symbol":"OKLO","account":"Margin","quantity":0,"peak":"EFM/I"},
                     {"symbol":"SMR","account":"Cash","quantity":100,"peak":"EFM/I"}]
        mapped = map_portfolio([row],watchlist)[0]
        self.assertEqual(mapped["watchlist_matches"],["OKLO"])
        self.assertEqual(mapped["outside_candidates"],["NEW"])
        self.assertEqual([h["account"] for h in mapped["holdings"]],["Cash"])
        self.assertIn("SMR",mapped["thematic_exposure"])

    def test_relevance_is_bounded(self):
        from app.options.prediction_markets import validate_research
        self.assertEqual(validate_research({"relevance":20})["relevance"],10)
        self.assertEqual(validate_research({"relevance":-4})["relevance"],0)

    def test_checkpoint_resume_and_publish(self):
        import tempfile
        from pathlib import Path
        from unittest.mock import patch
        from app.options import prediction_markets as pm
        with tempfile.TemporaryDirectory() as folder:
            with patch("app.options.api.watchlist_db_path",return_value=Path(folder)/"watch.sqlite3"):
                cp=pm.begin_checkpoint()
                page=[{"id":"1","question":"AI chips","active":True,"closed":False},
                      {"id":"2","question":"Closed","active":True,"closed":True}]
                cp=pm.persist_page(cp,page,"next")
                self.assertEqual(pm.checkpoint(),cp)
                self.assertEqual(pm.latest(),(None,[]))
                scan,rows=pm.latest(True)
                self.assertTrue(scan["partial"])
                self.assertEqual([r["id"] for r in rows],["1"])
                with self.assertRaises(ValueError):
                    pm.persist_page(cp,page,"next")
                self.assertEqual(pm.checkpoint(),cp)
                cp=pm.persist_page(cp,[{"id":"3","question":"Nuclear","active":True,"closed":False}],None)
                self.assertEqual(pm.finish_checkpoint(cp),2)
                self.assertIsNone(pm.checkpoint())
                scan,rows=pm.latest()
                self.assertEqual(scan["count"],2)
                self.assertEqual({r["id"] for r in rows},{"1","3"})

    def test_daily_request_cap(self):
        import tempfile
        from pathlib import Path
        from unittest.mock import patch
        from app.options import prediction_markets as pm
        with tempfile.TemporaryDirectory() as folder:
            with patch("app.options.api.watchlist_db_path",return_value=Path(folder)/"watch.sqlite3"), patch.dict("os.environ",{"RHTC_PREDICTION_DAILY_REQUESTS":"1","RHTC_PREDICTION_DAILY_TOKENS":"1000"}):
                self.assertIsNotNone(pm.reserve_request())
                self.assertIsNone(pm.reserve_request())
                self.assertEqual(pm.daily_usage()["unknown_usage"],1)

    def test_json_mode_input_and_response_validation(self):
        from types import SimpleNamespace
        import json
        from app.options import prediction_markets as pm
        self.assertIn("json",pm.semantic_input([{"id":"1"}]).lower())
        batch=[pm.normalize({"id":"1","question":"AI chips"}),pm.normalize({"id":"2","question":"Grid"})]
        result=SimpleNamespace(status="completed",output_text=json.dumps({"items":[{"id":"1","relevance":8},{"id":"1","relevance":2},{"id":"other","relevance":9},{"id":"2"}]}))
        records=pm.validated_batch_items(result,batch)
        self.assertEqual(len(records),1)
        self.assertEqual(records[0][0],"1")
        self.assertEqual(json.loads(records[0][2])["relevance"],8)
        with self.assertRaises(ValueError):
            pm.validated_batch_items(SimpleNamespace(status="incomplete",output_text="{}"),batch)
        with self.assertRaises(ValueError):
            pm.validated_batch_items(SimpleNamespace(status="completed",output_text='{"items":[]}'),batch)
