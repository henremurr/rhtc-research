import asyncio
import unittest
import httpx
from app.options import kalshi_provider as k


class KalshiProviderTests(unittest.TestCase):
    def test_normalization(self):
        row = k.normalize({"ticker": "TEST", "title": "Test event",
            "yes_bid_dollars": ".60", "yes_ask_dollars": ".70",
            "yes_bid_size_fp": "10", "yes_ask_size_fp": "20",
            "volume_24h_fp": "123.50", "open_interest_fp": "456",
            "rules_primary": "Primary", "rules_secondary": "Secondary"})
        self.assertEqual(row["id"], "kalshi:TEST")
        self.assertEqual(row["provider"], "kalshi")
        self.assertAlmostEqual(row["probabilities"]["Yes"], .65)
        self.assertAlmostEqual(row["probabilities"]["No"], .35)
        self.assertEqual(row["volume24h"], 123.5)
        self.assertEqual(row["volume_unit"], "contracts")
        self.assertEqual(row["open_interest"], 456)
        self.assertIn("Secondary", row["description"])

    def test_invalid_or_missing_quote(self):
        for bid, ask, size in [("NaN", ".8", "10"), (".9", ".2", "10"),
                               (".1", "1.2", "10"), (".1", ".2", "0")]:
            row = k.normalize({"ticker": "TEST", "yes_bid_dollars": bid,
                "yes_ask_dollars": ask, "yes_bid_size_fp": size, "yes_ask_size_fp": "10"})
            self.assertEqual(row["probabilities"], {})
            self.assertIsNone(row["spread"])

    def test_pagination(self):
        async def run():
            def handler(request):
                self.assertEqual(request.method, "GET")
                self.assertEqual(request.url.params["status"], "open")
                cursor = request.url.params.get("cursor")
                return httpx.Response(200, json={"markets": [{"ticker": "B" if cursor else "A"}],
                    "cursor": "" if cursor else "next"})
            async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
                page, cursor = await k.fetch_page(client)
                self.assertEqual(page[0]["ticker"], "A")
                page, cursor = await k.fetch_page(client, cursor)
                self.assertEqual(page[0]["ticker"], "B")
                self.assertIsNone(cursor)
        asyncio.run(run())

    def test_repeated_cursor(self):
        async def run():
            async with httpx.AsyncClient(transport=httpx.MockTransport(
                    lambda request: httpx.Response(200, json={"markets": [{"ticker": "A"}], "cursor": "same"}))) as client:
                with self.assertRaisesRegex(ValueError, "stopped advancing"):
                    await k.fetch_page(client, "same")
        asyncio.run(run())

    def test_quality_gates(self):
        from datetime import datetime, timezone, timedelta
        market = {"ticker": "TEST", "yes_bid_dollars": ".50", "yes_ask_dollars": ".52",
                  "yes_bid_size_fp": "100", "yes_ask_size_fp": "100",
                  "volume_24h_fp": "1000", "open_interest_fp": "1000",
                  "liquidity_dollars": "10000", "rules_primary": "Rules",
                  "updated_time": datetime.now(timezone.utc).isoformat()}
        self.assertEqual(k.normalize(market)["quality"], "higher liquidity")
        for change in ({"yes_bid_size_fp": "99"}, {"volume_24h_fp": "999"},
                       {"open_interest_fp": "999"}, {"liquidity_dollars": "9999"},
                       {"yes_ask_dollars": ".6"}, {"rules_primary": ""},
                       {"updated_time": (datetime.now(timezone.utc)-timedelta(hours=2)).isoformat()}):
            self.assertEqual(k.normalize(market | change)["quality"], "limited")
