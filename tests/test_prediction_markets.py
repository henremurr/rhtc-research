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

    def test_search_requires_contract_text_instead_of_thematic_exposure(self):
        import json
        import tempfile
        from pathlib import Path
        from unittest.mock import patch
        from app.options import prediction_markets as pm

        rows = [
            {"id": "1", "question": "Warriors vs. Trail Blazers", "description": "Basketball game"},
            {"id": "2", "question": "Will Oklo file an application?"},
            {"id": "3", "question": "New reactor licensing", "description": "Resolves based on a filing by Oklo Inc."},
            {"id": "4", "question": "Different company", "description": "A company named Roklo"},
        ]
        for row in rows:
            row.update(active=True, closed=False)
        with tempfile.TemporaryDirectory() as folder, \
             patch("app.options.api.watchlist_db_path", return_value=Path(folder) / "watch.sqlite3"), \
             patch("app.options.api.read_watchlist", return_value=[]):
            checkpoint = pm.persist_page(pm.begin_checkpoint(), rows, None)
            pm.finish_checkpoint(checkpoint)
            with pm.connect() as db:
                # Exercise a legacy inline row alongside current compact snapshots.
                row = pm.normalize(rows[2])
                row["thematic_exposure"] = ["OKLO"]
                db.execute("UPDATE snapshots SET payload=? WHERE id=?", (json.dumps(row), row["id"]))
            result = pm.markets(q="  $oklo  ", offset=0, limit=1, sort="volume")
            next_page = pm.markets(q="oklo", offset=1, limit=1, sort="volume")
            self.assertEqual(result["count"], 2)
            self.assertEqual([row["id"] for row in result["markets"]], ["2"])
            self.assertEqual([row["id"] for row in next_page["markets"]], ["3"])
            self.assertEqual(pm.markets(q="absent", offset=0, limit=10)["markets"], [])

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

    def test_compact_snapshot_preserves_legacy_and_versioned_rules(self):
        import json
        from app.options import prediction_markets as pm
        original=pm.normalize({"id":"1","question":"AI chips","description":"Original rules","outcomes":["Yes","No"],"outcomePrices":["0.6","0.4"]})
        key,meta,payload=pm.compact_snapshot(original)
        changed={**original,"probabilities":{"Yes":0.8,"No":0.2}}
        key2,meta2,payload2=pm.compact_snapshot(changed)
        self.assertEqual(key,key2)
        self.assertEqual(meta,meta2)
        self.assertNotIn("description",json.loads(payload))
        self.assertEqual(pm.hydrate_snapshot(payload,{key:meta}),original)
        self.assertEqual(pm.hydrate_snapshot(payload2,{key:meta}),changed)
        self.assertEqual(pm.hydrate_snapshot(json.dumps(original),{}),original)
        revised={**changed,"description":"Revised rules"}
        key3,meta3,payload3=pm.compact_snapshot(revised)
        self.assertNotEqual(key,key3)
        self.assertEqual(pm.hydrate_snapshot(payload3,{key3:meta3}),revised)
        with self.assertRaises(ValueError):
            pm.hydrate_snapshot(payload,{})

    def test_request_ledger_settlement(self):
        import tempfile
        from pathlib import Path
        from unittest.mock import patch
        from types import SimpleNamespace
        from app.options import prediction_markets as pm
        with tempfile.TemporaryDirectory() as folder:
            with patch("app.options.api.watchlist_db_path",return_value=Path(folder)/"watch.sqlite3"), patch.dict("os.environ",{"RHTC_PREDICTION_DAILY_REQUESTS":"10","RHTC_PREDICTION_DAILY_TOKENS":"1000"}):
                request=pm.reserve_request()
                self.assertEqual(pm.daily_usage()["in_flight"],1)
                self.assertEqual(pm.daily_usage()["unresolved_usage"],0)
                result=SimpleNamespace(usage=SimpleNamespace(input_tokens=25,output_tokens=10))
                self.assertTrue(pm.record_usage(request,result))
                self.assertFalse(pm.record_usage(request,result))
                self.assertEqual(pm.daily_usage()["input_tokens"],25)
                rejected=pm.reserve_request()
                pm.record_request_failure(rejected,SimpleNamespace(status_code=400))
                self.assertEqual(pm.daily_usage()["rejected"],1)
                self.assertEqual(pm.daily_usage()["unresolved_usage"],0)
                interrupted=pm.reserve_request()
                pm.recover_request_ledger()
                self.assertEqual(pm.daily_usage()["in_flight"],0)
                self.assertEqual(pm.daily_usage()["unresolved_usage"],1)

    def test_research_batch_size_and_priority(self):
        from unittest.mock import patch
        from app.options import prediction_markets as pm
        with patch.dict("os.environ", {"RHTC_PREDICTION_BATCH_SIZE": "16"}):
            self.assertEqual(pm.research_batch_size(),16)
        with patch.dict("os.environ", {"RHTC_PREDICTION_BATCH_SIZE": "999"}):
            self.assertEqual(pm.research_batch_size(),20)
        def row(mid, provider="polymarket", title="Event", topics=(), movement=0):
            return dict(id=mid, provider=provider, title=title, description="",
                        topics=list(topics), quality="limited", liquidity=0,
                        changes_pp={"1":{"Yes":movement}})
        rows=[row("macro",topics=["Macro"]),row("held","kalshi","Will OKLO report?"),
              row("static",topics=["AI/I"]),row("moving","kalshi",topics=["AI/I"],movement=12)]
        ordered=pm.prioritize_pending(rows,{"OKLO"},16)
        self.assertEqual([r["id"] for r in ordered],["held","moving","static","macro"])

    def test_provider_balance_and_exploration(self):
        from app.options import prediction_markets as pm
        rows=[dict(id=str(i),provider="polymarket" if i<20 else "kalshi",
                   title="Event",description="",topics=["AI/I"],quality="limited",
                   liquidity=0) for i in range(40)]
        rows.extend(dict(id="extra"+str(i),title="Other event",description="",topics=[],
                         quality="limited",liquidity=0) for i in range(10))
        ordered=pm.prioritize_pending(rows,set(),2)
        self.assertEqual(len({r["id"] for r in ordered}),50)
        self.assertNotEqual(ordered[0]["provider"],ordered[1]["provider"])
        self.assertTrue(all(not r["topics"] for r in ordered[8:10]))
