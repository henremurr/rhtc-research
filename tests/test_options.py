import asyncio
import os
import sqlite3
import tempfile
import unittest
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

    def test_watchlist_updates_persist_across_requests_and_drive_dashboard_scan(self):
        symbols = [
            {"symbol": "MU", "peak": "AI/I", "share_price": 128.5, "quantity": 100},
            {"symbol": "NEWCO", "peak": "Other", "share_price": None, "quantity": 4},
        ]
        with patch.dict(os.environ, {"RHTC_WATCHLIST_ADMIN_TOKEN": "test-admin"}, clear=False):
            saved = self.request("PUT", "/options/api/watchlist", headers={"X-RHTC-Admin-Token": "test-admin"}, json={"rows": symbols})
            response = self.request("GET", "/options/api/opportunities?limit=200")
            chain = self.request("GET", "/options/api/chain/NEWCO")
            reloaded = self.request("GET", "/options/api/watchlist")
        self.assertEqual(saved.status_code, 200)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["total"], 2)
        self.assertEqual({row["symbol"] for row in data["rows"]}, {"MU", "NEWCO"})
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
        async def provider_get(provider, path, params):
            if path.endswith("/quotes"):
                return {"quotes": {"quote": {"last": 100, "change_percentage": 1}}}
            if path.endswith("/expirations"):
                return {"expirations": {"date": ["2099-01-01"]}}
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
            capped = self.request("GET", "/options/api/opportunities?limit=127").json()
        self.assertEqual(capped["count"], 10)

        async def failing_get(provider, path, params):
            raise httpx.ConnectError("provider offline")
        with patch.dict(os.environ, {"TRADIER_API_TOKEN": "test-token"}, clear=True), patch.object(Tradier, "get", failing_get):
            data = self.request("GET", "/options/api/opportunities?limit=1").json()
        self.assertEqual(data["rows"][0]["source"], "error")
        self.assertNotIn("premium_yield", data["rows"][0])

    def test_chain_pages_through_four_expiration_sets(self):
        expiries = ["2099-01-01", "2099-01-08", "2099-01-15", "2099-01-22", "2099-01-29", "2099-02-05"]

        async def provider_get(provider, path, params):
            if path.endswith("/quotes"):
                return {"quotes": {"quote": {"last": 100, "change_percentage": 1}}}
            if path.endswith("/expirations"):
                return {"expirations": {"date": expiries}}
            if params["expiration"] in expiries[:2]:
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
        self.assertEqual([row["expiry"] for row in data["rows"]], expiries[2:])
        self.assertTrue(all(row["strike"] == 105 for row in data["rows"]))

    def test_demo_chain_has_four_pages(self):
        with patch.dict(os.environ, {}, clear=True):
            response = self.request("GET", "/options/api/chain/MU")
        rows = response.json()["rows"]
        self.assertEqual(len(rows), 4)
        self.assertEqual([row["dte"] for row in rows], [12, 19, 26, 33])
        self.assertTrue(all(row["strike"] > row["price"] for row in rows))

    def test_main_table_can_select_each_demo_expiration_set(self):
        with patch.dict(os.environ, {}, clear=True):
            first = self.request("GET", "/options/api/opportunities?limit=1&expiration_set=1").json()["rows"][0]
            third = self.request("GET", "/options/api/opportunities?limit=1&expiration_set=3").json()["rows"][0]
        self.assertNotEqual(first["expiry"], third["expiry"])
        self.assertEqual(third["dte"], 26)

    def test_tradier_main_table_selects_requested_expiration(self):
        expiries = ["2099-01-01", "2099-01-08", "2099-01-15", "2099-01-22"]

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


if __name__ == "__main__":
    unittest.main()
