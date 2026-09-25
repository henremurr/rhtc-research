import asyncio
import os
import sqlite3
import tempfile
import unittest
from datetime import date, timedelta
from unittest.mock import patch

import httpx

from main import app
from app.options.api import Tradier, WATCHLIST


class OptionsRoutesTest(unittest.TestCase):
    def setUp(self):
        self.data_dir = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.data_dir.cleanup()

    def request(self, method, path, **kwargs):
        async def run():
            with patch.dict(os.environ, {"RHTC_DATA_DIR": self.data_dir.name, "RAILWAY_VOLUME_MOUNT_PATH": self.data_dir.name}, clear=False):
                async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
                    return await client.request(method, path, **kwargs)
        return asyncio.run(run())

    def test_existing_routes_and_dashboard_assets(self):
        self.assertEqual(self.request("GET", "/health").status_code, 200)
        page = self.request("GET", "/options/")
        self.assertEqual(page.status_code, 200)
        self.assertIn("/options/static/app.js", page.text)
        self.assertIn('id="new-share-price"', page.text)
        self.assertIn('id="new-quantity"', page.text)
        self.assertIn('<option value="income">Highest income</option>', page.text)
        self.assertIn('id="review-limit"', page.text)
        self.assertIn('id="max-last"', page.text)
        self.assertIn('data-peak="Holdings"', page.text)
        self.assertIn('id="sidebar-toggle"', page.text)
        self.assertIn('aria-label="Collapse navigation"', page.text)
        self.assertIn('<h1>Covered Call Screening Tool</h1>', page.text)
        self.assertNotIn('Options overview', page.text)
        self.assertNotIn('Nearest out-of-the-money call for the selected expiration set', page.text)
        self.assertNotIn('<span>Calls to review</span>', page.text)
        self.assertIn('<option value="10" selected>10</option>', page.text)
        self.assertIn('<option value="200">All</option>', page.text)
        self.assertIn('title="Cost basis: share price × quantity from Manage symbols">COST</th>', page.text)
        self.assertEqual(self.request("GET", "/options/static/app.js").status_code, 200)
        self.assertEqual(self.request("GET", "/options/api/health").json()["watchlist_count"], 129)

    def test_demo_scan_and_summary(self):
        with patch.dict(os.environ, {}, clear=True):
            response = self.request("GET", "/options/api/opportunities?limit=2")
            data = response.json()
            self.assertEqual(data["source"], "demo")
            self.assertEqual(data["count"], 2)
            self.assertEqual(data["total"], len(WATCHLIST))
            self.assertTrue(all(row["quote_time"] == "DEMO DATA" for row in data["rows"]))
            summary = self.request("POST", "/options/api/summary", json={"source": "demo", "rows": data["rows"]})
            self.assertEqual(summary.json()["mode"], "rules")
            self.assertIn("Illustrative", summary.json()["summary"])

    def test_max_last_ceiling_filters_screen_and_blank_leaves_it_unfiltered(self):
        with patch.dict(os.environ, {}, clear=True):
            all_rows = self.request("GET", "/options/api/opportunities?limit=200").json()
            capped = self.request("GET", "/options/api/opportunities?limit=200&max_last=20").json()
            zero = self.request("GET", "/options/api/opportunities?limit=200&max_last=0").json()

        self.assertEqual(all_rows["count"], len(all_rows["rows"]))
        self.assertGreater(all_rows["count"], capped["count"])
        self.assertTrue(capped["rows"])
        self.assertTrue(all(row["price"] <= 20 for row in capped["rows"]))
        self.assertIn("ET", {row["symbol"] for row in capped["rows"]})
        self.assertEqual(zero["count"], 0)
        self.assertEqual(zero["rows"], [])
        invalid = self.request("GET", "/options/api/opportunities?max_last=-1")
        self.assertEqual(invalid.status_code, 422)

    def test_income_sort_orders_rows_by_bid_ask_midpoint_times_contract_multiplier(self):
        with patch.dict(os.environ, {}, clear=True):
            response = self.request("GET", "/options/api/opportunities?limit=200&sort=income")
        self.assertEqual(response.status_code, 200)
        rows = response.json()["rows"]
        incomes = [((row["bid"] + row["ask"]) / 2) * 100 for row in rows]
        self.assertEqual(incomes, sorted(incomes, reverse=True))

    def test_watchlist_updates_persist_across_requests_and_drive_dashboard_scan(self):
        symbols = [
            {"symbol": "NEWCO", "peak": "Other", "share_price": None, "quantity": 4},
            {"symbol": "MU", "peak": "AI/I", "share_price": 128.5, "quantity": 100},
        ]
        with patch.dict(os.environ, {"RHTC_WATCHLIST_ADMIN_TOKEN": "test-admin"}, clear=False):
            saved = self.request("PUT", "/options/api/watchlist", headers={"X-RHTC-Admin-Token": "test-admin"}, json={"rows": symbols})
            response = self.request("GET", "/options/api/opportunities?limit=200")
            holdings = self.request("GET", "/options/api/opportunities?holdings_only=true&limit=1")
            chain = self.request("GET", "/options/api/chain/NEWCO")
            reloaded = self.request("GET", "/options/api/watchlist")
        self.assertEqual(saved.status_code, 200)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["total"], 2)
        self.assertEqual({row["symbol"] for row in data["rows"]}, {"MU", "NEWCO"})
        by_symbol = {row["symbol"]: row for row in data["rows"]}
        self.assertEqual((by_symbol["MU"]["share_price"], by_symbol["MU"]["quantity"]), (128.5, 100))
        self.assertEqual((by_symbol["NEWCO"]["share_price"], by_symbol["NEWCO"]["quantity"]), (None, 4))
        self.assertEqual(holdings.json()["count"], 1)
        self.assertEqual(holdings.json()["rows"][0]["symbol"], "MU")
        self.assertEqual(reloaded.json()["rows"], symbols)
        self.assertFalse(reloaded.json()["migration_open"])
        self.assertEqual(chain.status_code, 200)
        self.assertEqual(chain.json()["symbol"], "NEWCO")

    def test_watchlist_migrates_old_database_and_allows_blank_holding_values(self):
        db_path = os.path.join(self.data_dir.name, "rhtc_symbols.sqlite3")
        with sqlite3.connect(db_path) as connection:
            connection.execute("CREATE TABLE symbols (position INTEGER PRIMARY KEY, symbol TEXT NOT NULL UNIQUE, peak TEXT NOT NULL)")
            connection.execute("CREATE TABLE app_state (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
            connection.execute("INSERT INTO symbols VALUES (0, 'MU', 'AI/I')")
            connection.execute("INSERT INTO app_state VALUES ('watchlist_seeded', '1')")
            connection.execute("INSERT INTO app_state VALUES ('legacy_import_open', '0')")
        old_rows = self.request("GET", "/options/api/watchlist").json()["rows"]
        self.assertEqual(old_rows, [{"symbol": "MU", "peak": "AI/I", "share_price": None, "quantity": None}])
        with patch.dict(os.environ, {"RHTC_WATCHLIST_ADMIN_TOKEN": "test-admin"}, clear=False):
            saved = self.request("PUT", "/options/api/watchlist", headers={"X-RHTC-Admin-Token": "test-admin"}, json={"rows": [{"symbol": "MU", "peak": "AI/I", "share_price": "", "quantity": ""}]})
            reloaded = self.request("GET", "/options/api/watchlist").json()["rows"]
        self.assertEqual(saved.status_code, 200)
        self.assertEqual(reloaded, [{"symbol": "MU", "peak": "AI/I", "share_price": None, "quantity": None}])

    def test_custom_symbol_list_rejects_duplicate_or_invalid_peaks(self):
        duplicate = [{"symbol": "MU", "peak": "AI/I"}, {"symbol": "MU", "peak": "Other"}]
        invalid_peak = [{"symbol": "MU", "peak": "Unknown"}]
        negative_quantity = [{"symbol": "MU", "peak": "AI/I", "quantity": -1}]
        with patch.dict(os.environ, {"RHTC_WATCHLIST_ADMIN_TOKEN": "test-admin"}, clear=False):
            for symbols in (duplicate, invalid_peak, negative_quantity):
                response = self.request("PUT", "/options/api/watchlist", headers={"X-RHTC-Admin-Token": "test-admin"}, json={"rows": symbols})
                self.assertEqual(response.status_code, 400)
            unauthorized = self.request("PUT", "/options/api/watchlist", json={"rows": []})
            self.assertEqual(unauthorized.status_code, 401)

    def test_empty_shared_watchlist_stays_empty(self):
        with patch.dict(os.environ, {"RHTC_WATCHLIST_ADMIN_TOKEN": "test-admin"}, clear=False):
            response = self.request("PUT", "/options/api/watchlist", headers={"X-RHTC-Admin-Token": "test-admin"}, json={"rows": []})
            reloaded = self.request("GET", "/options/api/watchlist")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(reloaded.json()["rows"], [])
        self.assertEqual(reloaded.json()["count"], 0)

    def test_tradier_selection_and_error_rows(self):
        expiries = [(date.today() + timedelta(days=days)).isoformat() for days in (3, 10, 17, 22)]
        async def provider_get(provider, path, params):
            if path.endswith("/quotes"):
                return {"quotes": {"quote": {"last": 100, "change_percentage": 1}}}
            if path.endswith("/expirations"):
                return {"expirations": {"date": expiries}}
            return {"options": {"option": [
                {"option_type": "call", "strike": 105, "bid": 2, "ask": 2.2, "open_interest": 80},
                {"option_type": "call", "strike": 110, "bid": 4, "ask": 4.2, "open_interest": 90},
            ]}}

        with patch.dict(os.environ, {"TRADIER_API_TOKEN": "test-token"}, clear=True), patch.object(Tradier, "get", provider_get):
            data = self.request("GET", "/options/api/opportunities?limit=1").json()
        self.assertEqual(data["source"], "tradier_sandbox")
        self.assertEqual(data["rows"][0]["strike"], 105)
        self.assertEqual(data["rows"][0]["premium_yield"], 2)

        with patch.dict(os.environ, {"TRADIER_API_TOKEN": "test-token"}, clear=True), patch.object(Tradier, "get", provider_get):
            expanded = self.request("GET", "/options/api/opportunities?limit=127").json()
        self.assertEqual(expanded["count"], 127)

        async def failing_get(provider, path, params):
            raise httpx.ConnectError("provider offline")
        with patch.dict(os.environ, {"TRADIER_API_TOKEN": "test-token"}, clear=True), patch.object(Tradier, "get", failing_get):
            data = self.request("GET", "/options/api/opportunities?limit=1").json()
        self.assertEqual(data["rows"][0]["source"], "error")
        self.assertNotIn("premium_yield", data["rows"][0])

    def test_chain_pages_through_four_expiration_sets(self):
        expiries = [(date.today() + timedelta(days=days)).isoformat() for days in (2, 5, 10, 17, 22)]

        async def provider_get(provider, path, params):
            if path.endswith("/quotes"):
                return {"quotes": {"quote": {"last": 100, "change_percentage": 1}}}
            if path.endswith("/expirations"):
                return {"expirations": {"date": expiries}}
            if params["expiration"] == expiries[0]:
                return {"options": {"option": []}}
            return {"options": {"option": [
                {"option_type": "call", "strike": 105, "bid": 2, "ask": 2.2, "open_interest": 80},
                {"option_type": "call", "strike": 110, "bid": 4, "ask": 4.2, "open_interest": 90},
            ]}}

        with patch.dict(os.environ, {"TRADIER_API_TOKEN": "test-token"}, clear=True), patch.object(Tradier, "get", provider_get):
            response = self.request("GET", "/options/api/chain/MU")

        data = response.json()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(data["source"], "tradier_sandbox")
        self.assertEqual([row["expiry"] for row in data["rows"]], expiries[1:])
        self.assertEqual([row["dte"] for row in data["rows"]], [5, 10, 17, 22])
        self.assertEqual([row["dte_window"] for row in data["rows"]], ["0-7 DTE", "8-14 DTE", "15-21 DTE", "22+ DTE"])
        self.assertTrue(all(row["strike"] == 105 for row in data["rows"]))

    def test_demo_chain_has_four_pages(self):
        with patch.dict(os.environ, {}, clear=True):
            response = self.request("GET", "/options/api/chain/MU")
        rows = response.json()["rows"]
        self.assertEqual(len(rows), 4)
        self.assertEqual([row["dte"] for row in rows], [7, 14, 21, 28])
        self.assertTrue(all(row["strike"] > row["price"] for row in rows))

    def test_main_table_can_select_each_demo_expiration_set(self):
        with patch.dict(os.environ, {}, clear=True):
            first = self.request("GET", "/options/api/opportunities?limit=1&expiration_set=1").json()["rows"][0]
            third = self.request("GET", "/options/api/opportunities?limit=1&expiration_set=3").json()["rows"][0]
        self.assertNotEqual(first["expiry"], third["expiry"])
        self.assertEqual(third["dte"], 21)

    def test_tradier_main_table_selects_requested_expiration(self):
        expiries = [(date.today() + timedelta(days=days)).isoformat() for days in (3, 10, 17, 22)]

        async def provider_get(provider, path, params):
            if path.endswith("/quotes"):
                return {"quotes": {"quote": {"last": 100}}}
            if path.endswith("/expirations"):
                return {"expirations": {"date": expiries}}
            strike = 100 + 5 * (expiries.index(params["expiration"]) + 1)
            return {"options": {"option": [{
                "option_type": "call", "strike": strike, "bid": 2,
                "ask": 2.2, "open_interest": 80,
            }]}}

        with patch.dict(os.environ, {"TRADIER_API_TOKEN": "test-token"}, clear=True), patch.object(Tradier, "get", provider_get):
            data = self.request("GET", "/options/api/opportunities?limit=1&expiration_set=3").json()
        self.assertEqual(data["rows"][0]["expiry"], expiries[2])
        self.assertEqual(data["rows"][0]["strike"], 115)
        self.assertEqual(data["rows"][0]["dte"], 17)

    def test_tradier_expiration_sets_keep_empty_dte_windows_visible(self):
        expiries = [(date.today() + timedelta(days=days)).isoformat() for days in (10, 17, 22)]

        async def provider_get(provider, path, params):
            if path.endswith("/quotes"):
                return {"quotes": {"quote": {"last": 100}}}
            if path.endswith("/expirations"):
                return {"expirations": {"date": expiries}}
            return {"options": {"option": [{
                "option_type": "call", "strike": 105, "bid": 2, "ask": 2.2,
                "open_interest": 80,
            }]}}

        with patch.dict(os.environ, {"TRADIER_API_TOKEN": "test-token"}, clear=True), patch.object(Tradier, "get", provider_get):
            chain = self.request("GET", "/options/api/chain/MU").json()["rows"]
            first = self.request("GET", "/options/api/opportunities?limit=1&expiration_set=1").json()["rows"][0]
        self.assertEqual(chain[0]["dte_window"], "0-7 DTE")
        self.assertIn("No listed expiration", chain[0]["error"])
        self.assertEqual(chain[1]["dte"], 10)
        self.assertIn("No listed expiration", first["error"])


if __name__ == "__main__":
    unittest.main()
