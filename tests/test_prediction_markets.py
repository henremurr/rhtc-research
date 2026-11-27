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
                offset = int(request.url.params["offset"])
                self.assertEqual(request.url.params["active"], "true")
                self.assertEqual(request.url.params["closed"], "false")
                page = [{"id": str(offset), "question": "Unfamiliar subject",
                         "active": True, "closed": False}] if offset < 2 else []
                return httpx.Response(200, json=page)
            async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
                rows = await discover(client)
            self.assertEqual(len(rows), 2)
            self.assertEqual(rows[0]["topics"], [])
        asyncio.run(run())

    def test_repeated_page_fails(self):
        async def run():
            def handler(request):
                return httpx.Response(200, json=[{"id":"1","active":True,"closed":False}])
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
