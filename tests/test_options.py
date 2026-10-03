import asyncio
import os
import sqlite3
import sys
import tempfile
import types
import unittest
from datetime import date, timedelta
from unittest.mock import patch

import httpx

from main import app
from app.options.api import Tradier, WATCHLIST, parse_finnhub_company_overview, parse_finnhub_metrics, format_option_contract, openai_error_message, split_speech_chunks, strip_mp3_metadata, record_stock_rating, split_stock_analysis_sections
from app.options import news


class OptionsRoutesTest(unittest.TestCase):
    def setUp(self):
        self.data_dir = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.data_dir.cleanup()

    def request(self, method, path, **kwargs):
        authenticated = kwargs.pop("authenticated", True)
        async def run():
            env = {"RHTC_DATA_DIR": self.data_dir.name, "RAILWAY_VOLUME_MOUNT_PATH": self.data_dir.name,
                   "RHTC_DASHBOARD_PASSWORD": "test-dashboard-password-long-enough"}
            with patch.dict(os.environ, env, clear=False):
                async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
                    if authenticated:
                        login = await client.post("/options/auth/login", json={"password": env["RHTC_DASHBOARD_PASSWORD"]})
                        if login.status_code != 200:
                            raise AssertionError(f"Test sign-in failed: {login.status_code} {login.text}")
                    return await client.request(method, path, **kwargs)
        return asyncio.run(run())

    def test_dashboard_requires_sign_in_for_pages_and_apis(self):
        page = self.request("GET", "/options/", authenticated=False)
        self.assertEqual(page.status_code, 303)
        self.assertTrue(page.headers["location"].startswith("/options/login?next="))
        self.assertEqual(self.request("GET", "/options/login", authenticated=False).status_code, 200)
        self.assertEqual(self.request("GET", "/options/api/watchlist", authenticated=False).status_code, 401)
        self.assertEqual(self.request("POST", "/options/api/symbol-analysis", json={"symbol": "BW"}, authenticated=False).status_code, 401)
        self.assertEqual(self.request("PUT", "/options/api/watchlist", json={"rows": []}, authenticated=False).status_code, 401)

    def test_dashboard_sign_in_and_sign_out(self):
        async def run():
            password = "test-dashboard-password-long-enough"
            with patch.dict(os.environ, {"RHTC_DASHBOARD_PASSWORD": password}, clear=False):
                async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
                    bad = await client.post("/options/auth/login", json={"password": "wrong"})
                    self.assertEqual(bad.status_code, 401)
                    good = await client.post("/options/auth/login", json={"password": password})
                    self.assertEqual(good.status_code, 200)
                    self.assertIn("httponly", good.headers["set-cookie"].lower())
                    self.assertIn("samesite=strict", good.headers["set-cookie"].lower())
                    self.assertEqual((await client.get("/options/")).status_code, 200)
                    await client.post("/options/auth/logout")
                    self.assertEqual((await client.get("/options/")).status_code, 303)
        asyncio.run(run())

    def test_dashboard_fails_closed_without_password(self):
        async def run():
            with patch.dict(os.environ, {"RHTC_DASHBOARD_PASSWORD": ""}, clear=False):
                async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
                    self.assertEqual((await client.get("/options/")).status_code, 303)
                    self.assertEqual((await client.get("/options/login")).status_code, 200)
                    self.assertEqual((await client.get("/options/api/watchlist")).status_code, 503)
        asyncio.run(run())

    def test_existing_routes_and_dashboard_assets(self):
        self.assertEqual(self.request("GET", "/health").status_code, 200)
        page = self.request("GET", "/options/")
        self.assertEqual(page.status_code, 200)
        self.assertIn("/options/static/app.js", page.text)
        self.assertIn('id="new-share-price"', page.text)
        self.assertIn('id="new-quantity"', page.text)
        self.assertIn('<option value="income" selected>Highest income</option>', page.text)
        self.assertLess(page.text.index('<option value="income" selected>'), page.text.index('<option value="premium_yield">'))
        self.assertIn('id="review-limit"', page.text)
        self.assertIn('id="max-last"', page.text)
        self.assertIn('<button id="add-symbol" type="button">+ Add</button>', page.text)
        self.assertIn('data-peak="Holdings"', page.text)
        self.assertIn('id="sidebar-toggle"', page.text)
        self.assertIn('aria-label="Collapse navigation"', page.text)
        self.assertIn('<h1>Covered Call Screening Tool</h1>', page.text)
        self.assertNotIn('Options overview', page.text)
        self.assertNotIn('Nearest out-of-the-money call for the selected expiration set', page.text)
        self.assertNotIn('<span>Calls to review</span>', page.text)
        self.assertIn('<option value="10" selected>10</option>', page.text)
        self.assertIn('<option value="200">All</option>', page.text)
        self.assertIn('<span>Rows</span><select id="review-limit" aria-label="Rows to display">', page.text)
        self.assertLess(page.text.index('id="search"'), page.text.index('<span>Rows</span>'))
        self.assertLess(page.text.index('<span>Rows</span>'), page.text.index('id="review-limit"'))
        self.assertIn('<span>Order by</span><select id="sort">', page.text)
        self.assertIn('<option value="stock_score">Stock score</option>', page.text)
        self.assertIn('<option value="call_score">Call score</option>', page.text)
        self.assertLess(page.text.index('<option value="stock_score">'), page.text.index('<option value="call_score">'))
        self.assertIn('<th title="Latest stock analysis rating: 1 Avoid · 2 Sell · 3 Watch · 4 Grow · 5 Bargain">STOCK / 5</th><th>CALL / 5</th><th title="Combined stock and call scores, each out of 5">RHTC / 10</th>', page.text)
        self.assertIn('>Analyze calls</button>', page.text)
        self.assertLess(page.text.index('Max Last'), page.text.index('<span>Order by</span>'))
        self.assertIn('app.css?v=readable-screener-20261003', page.text)
        self.assertIn('app.js?v=rhtc-score-20261003', page.text)
        self.assertIn('app.css?v=readable-screener-20261003', page.text)
        self.assertIn('app.js?v=rhtc-score-20261003', page.text)
        self.assertIn('id="analysis-mp3-btn"', page.text)
        self.assertIn('id="analysis-podcast-transcript"', page.text)
        self.assertIn('data-filter="news"', page.text)
        self.assertIn('id="news-view"', page.text)
        self.assertIn('id="news-items"', page.text)
        self.assertIn('id="symbol-analysis-modal"', page.text)
        self.assertLess(page.text.index('id="symbol-analysis-body"'), page.text.index('class="analysis-podcast-controls"'))
        self.assertIn('height:22vh;min-height:130px;max-height:180px', css)
        self.assertIn('analysis-modal-backdrop', page.text)
        self.assertIn('.analysis-modal-backdrop{align-items:flex-start}', css)
        self.assertIn('max-height:calc(100dvh - env(safe-area-inset-top)', css)
        self.assertIn('.analysis-modal>.modal-close{position:sticky', css)
        self.assertIn('width:44px;height:44px', css)
        self.assertIn('id="analysis-read-btn"', page.text)
        self.assertIn('id="analysis-stop-btn"', page.text)
        self.assertIn('id="detail-description"', page.text)

        self.assertNotIn('<th>CHG $</th>', page.text)
        self.assertNotIn('<th>CHG %</th>', page.text)
        self.assertIn('title="Share price saved in Manage symbols">COST</th>', page.text)
        self.assertIn('colspan="13"', page.text)
        self.assertLess(page.text.index('>CALL CONTRACT</th>'), page.text.index('<th>QTY</th>'))
        self.assertLess(page.text.index('<th>QTY</th>'), page.text.index('>BID / ASK</th>'))
        self.assertNotIn('<th></th>', page.text)
        script = self.request("GET", "/options/static/app.js").text
        self.assertIn('data-news-action="analyze"', script)
        self.assertIn("/options/api/news/analyze", script)
        self.assertIn("sort:'income'", script)
        self.assertIn('ticker-details-btn', script)
        self.assertNotIn('data-label="Change $"', script)
        self.assertNotIn('data-label="Change %"', script)
        self.assertIn('id="detail-quote-content"', page.text)
        self.assertIn('.detail-modal>.modal-close{position:sticky', css)
        self.assertIn('width:44px;height:44px', css)
        self.assertIn('-webkit-overflow-scrolling:touch', css)
        self.assertIn("fetch('/options/api/quote/'+encodeURIComponent(symbol))", script)
        self.assertIn("quoteCell('52-H',quote.week_52_high)", script)
        self.assertIn("quoteCell('52-L',quote.week_52_low)", script)
        quote_order = [
            "quoteCell('Day high',quote.high)",
            "quoteCell('Day low',quote.low)",
            "quoteCell('Volume',quote.volume,'volume')",
            "quoteCell('52-H',quote.week_52_high)",
            "quoteCell('52-L',quote.week_52_low)",
            "quoteCell('Average volume',quote.average_volume,'volume')",
            "quoteCell('Previous close',quote.previous_close)",
            "quoteCell('Market cap',quote.market_cap,'marketcap')",
            "quoteCell('P/E ratio',quote.price_earnings_ratio,'ratio')",
        ]
        self.assertEqual(sorted(quote_order, key=script.index), quote_order)
        self.assertIn('detail-call-block', script)
        self.assertIn('Expiration date', script)
        self.assertIn('Days to expiration', script)
        self.assertIn('/options/api/quote/', script)
        self.assertIn('<button class="ticker-details-btn" title="View ${safe(r.symbol)} option details"', script)
        self.assertIn('>${safe(r.symbol)}</button>', script)
        self.assertIn('title="View ${safe(r.symbol)} option details" aria-label="View ${safe(r.symbol)} option details"', script)
        self.assertIn('class="ticker-ai-btn"', script)
        self.assertIn('aria-label="Open ChatGPT deep analysis for ${safe(r.symbol)}"', script)
        self.assertIn('function analysisTotalScore(lines)', script)
        self.assertIn('function analysisScorecardMarkup(line)', script)
        self.assertIn('class="analysis-score-token analysis-score-${score}"', script)
        self.assertIn('.analysis-scorecard{display:flex', css)
        self.assertIn('rhtc-score-20261003', page.text)
        self.assertIn('Total score: ${totalScore} out of 5', script)
        self.assertIn('async function analyzeSymbol(symbol)', script)
        self.assertIn('contractParts.push(`${fmt(strike)} Call`)', script)
        self.assertIn("month:'short',day:'numeric',year:'numeric'", script)
        self.assertIn('function toggleAnalysisSpeech()', script)
        self.assertIn('read.hidden=!supported', script)
        self.assertIn("$('#analysis-read-btn').addEventListener('click',toggleAnalysisSpeech)", script)
        self.assertIn("$('#analysis-stop-btn').addEventListener('click',()=>stopAnalysisSpeech())", script)
        self.assertIn("$('#analysis-mp3-btn').addEventListener('click',createAnalysisPodcast)", script)
        self.assertIn("/options/api/analysis-podcast/transcript", script)
        self.assertIn("/options/api/analysis-podcast/audio", script)
        self.assertIn("window.hideSymbolAnalysis=()=>{stopAnalysisSpeech();", script)
        self.assertIn("description.textContent=state.chainDescription", script)
        self.assertNotIn('title="View chain"', script)
        for label in ('Ticker', 'Peak', 'Stock score', 'Call score', 'Last', 'Change $', 'Change %', 'Cost', 'Call contract', 'Qty', 'Bid / ask', 'Bid / ask yield', 'Income', 'OI / Vol'):
            self.assertIn(f'data-label="{label}"', script)
        self.assertIn('function quantityForPrice(price)', script)
        self.assertIn('Math.trunc(ceiling/last)', script)
        self.assertIn('function incomeForRow(row)', script)
        self.assertIn('rows=rows.filter(r=>!r.error)', script)
        self.assertIn('No symbols with call data match the selected filters.', script)
        self.assertIn("<b>${safe(contractLabel(r))}</b>", script)
        self.assertIn('return ((bid+ask)/2)*100*quantityForPrice(row.price)', script)
        self.assertIn('const cost=r.share_price!==null', script)
        self.assertNotIn('Number(r.share_price)*Number(r.quantity)', script)
        self.assertIn("else if(state.sort==='income')", script)
        self.assertIn('return bi-ai', script)
        self.assertIn('SpeechSynthesisUtterance', script)
        self.assertIn('function toggleNewsSpeech(card)', script)
        self.assertIn('window.speechSynthesis.pause()', script)
        self.assertIn('function stopNewsSpeech', script)
        css = self.request("GET", "/options/static/app.css").text
        self.assertIn('.review-limit-control{height:31px;display:flex;align-items:center;', css)
        self.assertIn('.sort-control{height:31px;display:flex;align-items:center;', css)
        self.assertIn('.ticker-details-btn{padding:0;border:0;background:transparent;', css)
        self.assertIn('.ticker-ai-btn{width:17px;height:17px;', css)
        self.assertIn('.news-read-btn,.news-stop-btn{min-height:32px;', css)
        self.assertIn('.analysis-modal{width:min(900px,calc(100vw - 32px));', css)
        self.assertIn('.analysis-score-1,.analysis-score-2{color:#b42318', css)
        self.assertIn('.analysis-score-3{color:#fff', css)
        self.assertIn('.analysis-score-4,.analysis-score-5{color:#067647', css)
        self.assertIn(':root[data-theme="dark"] .symbol-add-form>button{width:120px;justify-self:start;background:#3b434c;color:#c4ced9;border-color:#525d69}', css)
        self.assertIn('@media(max-width:800px){.symbols-modal{padding:20px 16px}.symbol-add-form{grid-template-columns:repeat(2,minmax(0,1fr))}', css)
        self.assertIn('table-layout:fixed', css)
        self.assertIn('th,td{white-space:normal;overflow-wrap:anywhere}', css)
        self.assertIn('@media(max-width:900px){.table-wrap{max-height:none;overflow:visible}', css)
        self.assertIn('.table-wrap{overflow-x:auto;overscroll-behavior-x:contain;touch-action:pan-x pan-y}', css)
        self.assertIn('.screener-table{table-layout:auto;min-width:0;width:100%}', css)
        self.assertIn('padding-left:1px;padding-right:1px', css)
        self.assertIn('overflow:visible;overflow-wrap:normal;text-overflow:initial', css)
        self.assertIn('.screener-table .number,.screener-table .quote,.screener-table .contract b,.screener-table .oi,.screener-table .quote-volume,.screener-table .yield-pill{font-size:10px}', css)
        self.assertEqual(self.request("GET", "/options/api/health").json()["watchlist_count"], 129)

    def test_news_feed_is_authenticated_and_uses_persistent_database(self):
        unauthorized = self.request("GET", "/options/api/news", authenticated=False)
        self.assertEqual(unauthorized.status_code, 401)
        response = self.request("GET", "/options/api/news")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["items"], [])
        self.assertFalse(response.json()["configured"])

    def test_news_scan_reports_missing_provider_key(self):
        with patch.dict(os.environ, {"PERPLEXITY_API_KEY": ""}, clear=False):
            response = self.request("POST", "/options/api/news/scan")
        self.assertEqual(response.status_code, 503)
        self.assertIn("PERPLEXITY_API_KEY", response.json()["detail"])

    def test_news_scan_requests_supported_max_and_caps_at_25_unique_articles(self):
        payloads = []

        class FakeResponse:
            def raise_for_status(self):
                pass

            def json(self):
                return {"results": [
                    {"title": f"Article {index}", "url": f"https://example.com/{index}"}
                    for index in range(40)
                ]}

        class FakeClient:
            def __init__(self, **kwargs):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                pass

            async def post(self, url, *, headers, json):
                payloads.append(json)
                return FakeResponse()

        async def run_scan():
            with patch.dict(os.environ, {"RHTC_DATA_DIR": self.data_dir.name, "PERPLEXITY_API_KEY": "test-key"}, clear=False):
                with patch.object(news.httpx, "AsyncClient", FakeClient):
                    return await news.scan_news(scheduled=True)

        result = asyncio.run(run_scan())
        self.assertEqual(payloads[0]["max_results"], 20)
        self.assertEqual(len(payloads[0]["query"]), 5)
        self.assertEqual(result["added"], 25)

    def test_news_scan_deduplicates_tracking_and_url_variants_across_scans(self):
        class FakeResponse:
            def raise_for_status(self):
                pass

            def json(self):
                return {"results": [
                    {"title": "A story", "url": "https://www.example.com/story/?utm_source=feed#top"},
                    {"title": "A story", "url": "https://example.com/story"},
                ]}

        class FakeClient:
            def __init__(self, **kwargs):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                pass

            async def post(self, url, *, headers, json):
                return FakeResponse()

        async def run_scan():
            env = {"RHTC_DATA_DIR": self.data_dir.name, "PERPLEXITY_API_KEY": "test-key"}
            with patch.dict(os.environ, env, clear=False):
                with patch.object(news.httpx, "AsyncClient", FakeClient):
                    first = await news.scan_news(scheduled=True)
                    second = await news.scan_news(scheduled=True)
                    return first, second

        first, second = asyncio.run(run_scan())
        self.assertEqual(first["added"], 1)
        self.assertEqual(second["added"], 0)
        self.assertEqual(second["total"], 1)
        with patch.dict(os.environ, {"RHTC_DATA_DIR": self.data_dir.name}, clear=False):
            connection = news.connect_db()
            rows = connection.execute("SELECT url FROM news_items").fetchall()
            connection.close()
        self.assertEqual([row["url"] for row in rows], ["https://example.com/story"])
    def test_news_db_migration_merges_existing_url_variants(self):
        path = os.path.join(self.data_dir.name, "rhtc_symbols.sqlite3")
        connection = sqlite3.connect(path)
        connection.execute("CREATE TABLE news_items (url TEXT PRIMARY KEY, title TEXT NOT NULL, source TEXT NOT NULL, published_at TEXT NOT NULL, snippet TEXT NOT NULL, peak TEXT NOT NULL, first_seen_at TEXT NOT NULL, last_seen_at TEXT NOT NULL)")
        connection.execute("CREATE TABLE news_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        connection.executemany(
            "INSERT INTO news_items VALUES(?,?,?,?,?,?,?,?)",
            [
                ("https://www.example.com/story/?utm_source=old", "Old title", "example.com", "", "", "Other", "2026-09-28T10:00:00-07:00", "2026-09-28T10:00:00-07:00"),
                ("https://example.com/story", "Latest title", "example.com", "", "", "Other", "2026-09-28T11:00:00-07:00", "2026-09-28T12:00:00-07:00"),
            ],
        )
        connection.commit()
        connection.close()

        with patch.dict(os.environ, {"RHTC_DATA_DIR": self.data_dir.name}, clear=False):
            connection = news.connect_db()
            rows = connection.execute("SELECT url,title,first_seen_at,last_seen_at FROM news_items").fetchall()
            connection.close()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["url"], "https://example.com/story")
        self.assertEqual(rows[0]["title"], "Latest title")
        self.assertEqual(rows[0]["first_seen_at"], "2026-09-28T10:00:00-07:00")
        self.assertEqual(rows[0]["last_seen_at"], "2026-09-28T12:00:00-07:00")
    def test_news_analysis_is_authenticated_and_maps_story_to_watchlist_and_thesis(self):
        payload = {
            "title": "New grid equipment contract",
            "url": "https://example.com/grid-award",
            "snippet": "The company won a contract to reinforce regional transmission.",
            "published_at": "2026-09-27",
        }
        denied = self.request("POST", "/options/api/news/analyze", authenticated=False, json=payload)
        self.assertEqual(denied.status_code, 401)

        class FakeResponses:
            async def create(self, **kwargs):
                self.kwargs = kwargs
                citation = types.SimpleNamespace(url="https://source.example.com/release", title="Company release")
                annotation = types.SimpleNamespace(type="url_citation", url_citation=citation)
                content = types.SimpleNamespace(annotations=[annotation])
                return types.SimpleNamespace(output=[types.SimpleNamespace(content=[content])], output_text="Thesis impact")

        responses = FakeResponses()
        fake_openai = types.SimpleNamespace(AsyncOpenAI=lambda **kwargs: types.SimpleNamespace(responses=responses))
        with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key", "OPENAI_ANALYSIS_MODEL": "test-model"}, clear=False):
            with patch.dict(sys.modules, {"openai": fake_openai}):
                with patch("app.options.api.read_watchlist", return_value=[
                    {"symbol": "ET", "peak": "EFM/I", "share_price": 18.5, "quantity": 1000},
                    {"symbol": "NOC", "peak": "DS/I", "share_price": 500, "quantity": 100},
                ]):
                    result = self.request("POST", "/options/api/news/analyze", json=payload)

        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.json()["analysis"], "Thesis impact")
        self.assertEqual(result.json()["citations"], [{"title": "Company release", "url": "https://source.example.com/release"}])
        self.assertEqual(responses.kwargs["tools"], [{"type": "web_search"}])
        self.assertIn("ET", responses.kwargs["input"])
        self.assertIn("NOC", responses.kwargs["input"])
        self.assertNotIn("18.5", responses.kwargs["input"])
        self.assertIn("AI/I", responses.kwargs["instructions"])
        self.assertIn("EFM/I", responses.kwargs["instructions"])
        self.assertIn("DS/I", responses.kwargs["instructions"])
        self.assertIn("untrusted source material", responses.kwargs["instructions"])
        self.assertIn("Overall Three Peaks thesis", responses.kwargs["instructions"])
        self.assertIn("direct/indirect", responses.kwargs["instructions"])

    def test_news_analysis_rejects_invalid_article_url_and_reports_missing_key(self):
        invalid = self.request("POST", "/options/api/news/analyze", json={"title": "Story", "url": "javascript:alert(1)"})
        self.assertEqual(invalid.status_code, 400)
        self.assertIn("valid web address", invalid.json()["detail"])
        with patch.dict(os.environ, {"OPENAI_API_KEY": ""}, clear=False):
            unavailable = self.request("POST", "/options/api/news/analyze", json={"title": "Story", "url": "https://example.com/story"})
        self.assertEqual(unavailable.status_code, 503)
        self.assertIn("OPENAI_API_KEY", unavailable.json()["detail"])

    def test_demo_scan_and_summary(self):
        with patch.dict(os.environ, {}, clear=True):
            response = self.request("GET", "/options/api/opportunities?limit=2")
            data = response.json()
            self.assertEqual(data["source"], "demo")
            self.assertEqual(data["count"], 2)
            self.assertEqual(data["total"], len(WATCHLIST))
            self.assertTrue(all(row["quote_time"] == "DEMO DATA" for row in data["rows"]))
            self.assertTrue(all(isinstance(row["change"], (int, float)) for row in data["rows"]))
            self.assertTrue(all(isinstance(row["change_pct"], (int, float)) for row in data["rows"]))
            self.assertTrue(all(row["contract"] == f"{row['expiry'].replace('-', '')}-{row['strike']:.1f}" for row in data["rows"]))
            summary = self.request("POST", "/options/api/summary", json={"source": "demo", "rows": data["rows"]})
            self.assertEqual(summary.json()["mode"], "rules")
            self.assertIn("Illustrative", summary.json()["summary"])


    def test_analysis_podcast_transcript_uses_source_analysis_and_enforces_limit(self):
        class FakeResponses:
            async def create(self, **kwargs):
                self.kwargs = kwargs
                return types.SimpleNamespace(output_text="Welcome to RHTC Policy & Power. This episode reviews the supplied analysis.")

        responses = FakeResponses()
        fake_openai = types.SimpleNamespace(AsyncOpenAI=lambda **kwargs: types.SimpleNamespace(responses=responses))
        with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key", "OPENAI_PODCAST_SCRIPT_MODEL": "test-script-model"}, clear=False):
            with patch.dict(sys.modules, {"openai": fake_openai}):
                result = self.request("POST", "/options/api/analysis-podcast/transcript", json={
                    "title": "MU · Deep analysis", "subtitle": "AI / Infrastructure", "analysis": "Source analysis has this verified fact."
                })
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.json()["character_count"], len(result.json()["transcript"]))
        self.assertLessEqual(result.json()["character_count"], 11500)
        self.assertEqual(responses.kwargs["model"], "test-script-model")
        self.assertIn("Source analysis has this verified fact.", responses.kwargs["input"])
        self.assertIn("under 11,500 characters", responses.kwargs["instructions"])

    def test_analysis_podcast_audio_splits_text_and_returns_mp3(self):
        calls = []

        class FakeSpeech:
            async def create(self, **kwargs):
                calls.append(kwargs)
                return types.SimpleNamespace(content=b"\\xff\\xfbframe" + bytes([len(calls)]))

        fake_openai = types.SimpleNamespace(AsyncOpenAI=lambda **kwargs: types.SimpleNamespace(audio=types.SimpleNamespace(speech=FakeSpeech())))
        transcript = "Opening sentence. " + ("careful podcast narration " * 220)
        self.assertEqual(strip_mp3_metadata(b"\\xff\\xfbframe"), b"\\xff\\xfbframe")
        chunks = split_speech_chunks(transcript)
        self.assertGreater(len(chunks), 1)
        self.assertTrue(all(len(chunk) <= 4096 for chunk in chunks))
        with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}, clear=False):
            with patch.dict(sys.modules, {"openai": fake_openai}):
                response = self.request("POST", "/options/api/analysis-podcast/audio", json={"title": "MU Deep Analysis", "transcript": transcript})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["content-type"], "audio/mpeg")
        self.assertIn("RHTC_mu-deep-analysis_Spotify.mp3", response.headers["content-disposition"])
        self.assertEqual(len(calls), len(chunks))
        self.assertTrue(all(call["model"] == "gpt-4o-mini-tts" and call["response_format"] == "mp3" for call in calls))
        self.assertTrue(all(len(call["input"]) <= 4096 for call in calls))
        self.assertEqual(response.content, b"".join(b"\\xff\\xfbframe" + bytes([i]) for i in range(1, len(calls) + 1)))

    def test_analysis_podcast_endpoints_require_dashboard_auth_and_openai_key(self):
        unauthorized = self.request("POST", "/options/api/analysis-podcast/transcript", authenticated=False, json={"title": "Story", "analysis": "Some analysis"})
        self.assertEqual(unauthorized.status_code, 401)
        with patch.dict(os.environ, {"OPENAI_API_KEY": ""}, clear=False):
            unavailable = self.request("POST", "/options/api/analysis-podcast/transcript", json={"title": "Story", "analysis": "Some analysis"})
        self.assertEqual(unavailable.status_code, 503)
        too_long = self.request("POST", "/options/api/analysis-podcast/audio", json={"title": "Story", "transcript": "x" * 11501})
        self.assertEqual(too_long.status_code, 422)

    def test_stock_analysis_sections_do_not_repeat_summary_in_details(self):
        analysis = (
            "Research note before sections.\n"
            "### Summary and rating\n"
            "**Rating: 3 — Watch**\n"
            "A concise company summary.\n"
            "### Detailed analysis\n"
            "#### Business and competitive position\n"
            "The company has a differentiated business."
        )
        summary, details = split_stock_analysis_sections(analysis)
        self.assertIn("A concise company summary.", summary)
        self.assertNotIn("Research note before sections.", summary)
        self.assertNotIn("Summary and rating", details)
        self.assertNotIn("A concise company summary.", details)
        self.assertIn("Business and competitive position", details)

    def test_symbol_analysis_requires_server_openai_key(self):
        with patch.dict(os.environ, {}, clear=True):
            response = self.request("POST", "/options/api/symbol-analysis", json={"symbol": "MU"})
        self.assertEqual(response.status_code, 503)
        self.assertIn("OPENAI_API_KEY", response.json()["detail"])

    def test_openai_errors_are_translated_into_actionable_messages(self):
        quota = types.SimpleNamespace(status_code=429, code="insufficient_quota", body=None)
        rejected = types.SimpleNamespace(status_code=401, code=None, body=None)
        model = types.SimpleNamespace(status_code=400, code=None, body=None)
        self.assertIn("billing or credits", openai_error_message(quota))
        self.assertIn("rejected the API key", openai_error_message(rejected))
        self.assertIn("model access", openai_error_message(model))

    def test_symbol_analysis_uses_web_search_and_returns_clickable_citations(self):
        class FakeResponses:
            async def create(self, **kwargs):
                self.kwargs = kwargs
                citation = types.SimpleNamespace(url="https://investor.example.com/", title="Investor Relations")
                annotation = types.SimpleNamespace(type="url_citation", url_citation=citation)
                content = types.SimpleNamespace(annotations=[annotation])
                return types.SimpleNamespace(output=[types.SimpleNamespace(content=[content])], output_text="Business analysis")

        responses = FakeResponses()
        fake_openai = types.SimpleNamespace(AsyncOpenAI=lambda **kwargs: types.SimpleNamespace(responses=responses))
        with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key", "OPENAI_ANALYSIS_MODEL": "test-model"}, clear=False):
            with patch.dict(sys.modules, {"openai": fake_openai}):
                result = self.request("POST", "/options/api/symbol-analysis", json={"symbol": "MU", "screen": {"price": 100, "ignored": "secret"}})
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.json()["analysis"], "Business analysis")
        self.assertEqual(result.json()["citations"], [{"title": "Investor Relations", "url": "https://investor.example.com/"}])
        self.assertEqual(responses.kwargs["tools"], [{"type": "web_search"}])
        self.assertIn('"price":100', responses.kwargs["input"])
        self.assertNotIn("secret", responses.kwargs["input"])
        self.assertIn("covered-call verdict", responses.kwargs["instructions"].lower())
        self.assertIn("in plain english", responses.kwargs["instructions"].lower())
        self.assertIn("verdict must be weak", responses.kwargs["instructions"].lower())
        self.assertGreaterEqual(responses.kwargs["max_output_tokens"], 12000)
        self.assertEqual(responses.kwargs["reasoning"], {"effort": "low"})

    def test_symbol_analysis_running_average_is_per_symbol_across_strikes(self):
        class FakeResponses:
            def __init__(self):
                self.outputs = [
                    "## Covered-call verdict\\nScorecard — Income: 4/5 · Upside cushion: 4/5 · Event risk: 4/5 · Liquidity: 4/5",
                    "## Covered-call verdict\\nScorecard — Income: 2/5 · Upside cushion: 2/5 · Event risk: 2/5 · Liquidity: 2/5",
                ]

            async def create(self, **kwargs):
                return types.SimpleNamespace(output=[], output_text=self.outputs.pop(0))

        fake_responses = FakeResponses()
        fake_openai = types.SimpleNamespace(AsyncOpenAI=lambda **kwargs: types.SimpleNamespace(responses=fake_responses))
        with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}, clear=False):
            with patch.dict(sys.modules, {"openai": fake_openai}):
                saved = self.request("PUT", "/options/api/watchlist", json={"rows": [{"symbol": "MU", "peak": "AI/I"}]})
                first = self.request("POST", "/options/api/symbol-analysis", json={"symbol": "MU", "screen": {"strike": 130, "expiry": "2026-10-02"}})
                second = self.request("POST", "/options/api/symbol-analysis", json={"symbol": "MU", "screen": {"strike": 150, "expiry": "2026-10-09"}})
                watchlist = self.request("GET", "/options/api/watchlist").json()["rows"]
                opportunities = self.request("GET", "/options/api/opportunities?limit=1").json()["rows"]

        self.assertEqual(saved.status_code, 200)
        self.assertEqual(first.json()["total_score"], 4)
        self.assertEqual(second.json()["total_score"], 2)
        self.assertEqual(second.json()["call_score"], 3)
        self.assertEqual(second.json()["analysis_count"], 2)
        self.assertEqual(watchlist[0]["call_score"], 3)
        self.assertEqual(watchlist[0]["analysis_count"], 2)
        self.assertEqual(opportunities[0]["call_score"], 3)

    def test_symbol_analysis_empty_model_output_returns_screen_verdict(self):
        class EmptyResponses:
            async def create(self, **kwargs):
                return types.SimpleNamespace(output=[], output_text="", status="incomplete")

        fake_openai = types.SimpleNamespace(AsyncOpenAI=lambda **kwargs: types.SimpleNamespace(responses=EmptyResponses()))
        screen = {"price": 9.41, "strike": 9.5, "dte": 6, "bid": .30, "ask": .38, "premium_yield": 3.19, "estimated_income": 170, "quantity": 5, "open_interest": 805, "volume": 99, "contract": "20261002-9.5"}
        with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}, clear=False):
            with patch.dict(sys.modules, {"openai": fake_openai}):
                result = self.request("POST", "/options/api/symbol-analysis", json={"symbol": "BW", "screen": screen})
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.json()["mode"], "screen_fallback")
        self.assertIn("In plain English", result.json()["analysis"])
        self.assertIn("Scorecard — Income:", result.json()["analysis"])
        self.assertIn("$170.00", result.json()["analysis"])

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
            response = self.request("GET", "/options/api/opportunities?limit=200")
        self.assertEqual(response.status_code, 200)
        rows = response.json()["rows"]
        incomes = [((row["bid"] + row["ask"]) / 2) * 100 for row in rows]
        self.assertEqual(incomes, sorted(incomes, reverse=True))

    def test_watchlist_updates_persist_across_requests_and_drive_dashboard_scan(self):
        symbols = [
            {"symbol": "NEWCO", "peak": "Other", "share_price": None, "quantity": 4},
            {"symbol": "MU", "peak": "AI/I", "share_price": 128.5, "quantity": 100},
        ]
        with patch.dict(os.environ, {"RHTC_WATCHLIST_ADMIN_TOKEN": ""}, clear=False):
            saved = self.request("PUT", "/options/api/watchlist", json={"rows": symbols})
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
        self.assertEqual(
            reloaded.json()["rows"],
            [{**row, "call_score": None, "analysis_count": 0, "stock_score": None, "stock_rating_label": None} for row in symbols],
        )
        self.assertIsNone(by_symbol["MU"]["call_score"])
        self.assertEqual(by_symbol["MU"]["analysis_count"], 0)
        self.assertFalse(reloaded.json()["migration_open"])
        self.assertTrue(reloaded.json()["editing_enabled"])
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
        self.assertEqual(old_rows, [{"symbol": "MU", "peak": "AI/I", "share_price": None, "quantity": None, "call_score": None, "analysis_count": 0, "stock_score": None, "stock_rating_label": None}])
        with patch.dict(os.environ, {"RHTC_WATCHLIST_ADMIN_TOKEN": ""}, clear=False):
            saved = self.request("PUT", "/options/api/watchlist", json={"rows": [{"symbol": "MU", "peak": "AI/I", "share_price": "", "quantity": ""}]})
            reloaded = self.request("GET", "/options/api/watchlist").json()["rows"]
        self.assertEqual(saved.status_code, 200)
        self.assertEqual(reloaded, [{"symbol": "MU", "peak": "AI/I", "share_price": None, "quantity": None, "call_score": None, "analysis_count": 0, "stock_score": None, "stock_rating_label": None}])

    def test_stock_rating_is_persisted_and_returned_with_opportunity_rows(self):
        with patch.dict(os.environ, {"RHTC_DATA_DIR": self.data_dir.name}, clear=False):
            self.assertTrue(record_stock_rating("MU", 4, "Grow"))
            self.assertTrue(record_stock_rating("OKLO", 5, "Bargain"))
            response = self.request("GET", "/options/api/opportunities?sort=stock_score&limit=200")
        self.assertEqual(response.status_code, 200)
        rows = response.json()["rows"]
        scored = [(row["symbol"], row["stock_score"]) for row in rows if row["stock_score"] is not None]
        self.assertEqual(scored, [("OKLO", 5), ("MU", 4)])
        mu = next(row for row in rows if row["symbol"] == "MU")
        self.assertEqual(mu["stock_rating_label"], "Grow")

    def test_call_score_migrates_legacy_average_total_score_database_column(self):
        db_path = os.path.join(self.data_dir.name, "rhtc_symbols.sqlite3")
        with sqlite3.connect(db_path) as connection:
            connection.execute(
                "CREATE TABLE symbols (position INTEGER PRIMARY KEY, symbol TEXT NOT NULL UNIQUE, peak TEXT NOT NULL, "
                "share_price REAL, quantity REAL, average_total_score REAL, analysis_count INTEGER NOT NULL DEFAULT 0)"
            )
            connection.execute(
                "INSERT INTO symbols(position, symbol, peak, average_total_score, analysis_count) VALUES (0, 'MU', 'AI/I', 3.75, 4)"
            )
            connection.execute("CREATE TABLE app_state (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
            connection.execute("INSERT INTO app_state VALUES ('watchlist_seeded', '1')")
            connection.execute("INSERT INTO app_state VALUES ('legacy_import_open', '0')")
        response = self.request("GET", "/options/api/watchlist")
        self.assertEqual(response.status_code, 200)
        row = response.json()["rows"][0]
        self.assertEqual(row["call_score"], 3.75)
        self.assertEqual(row["analysis_count"], 4)
        with sqlite3.connect(db_path) as connection:
            columns = {row[1] for row in connection.execute("PRAGMA table_info(symbols)")}
        self.assertIn("call_score", columns)
        self.assertNotIn("average_total_score", columns)

    def test_custom_symbol_list_rejects_duplicate_or_invalid_peaks(self):
        duplicate = [{"symbol": "MU", "peak": "AI/I"}, {"symbol": "MU", "peak": "Other"}]
        invalid_peak = [{"symbol": "MU", "peak": "Unknown"}]
        negative_quantity = [{"symbol": "MU", "peak": "AI/I", "quantity": -1}]
        with patch.dict(os.environ, {"RHTC_WATCHLIST_ADMIN_TOKEN": ""}, clear=False):
            for symbols in (duplicate, invalid_peak, negative_quantity):
                response = self.request("PUT", "/options/api/watchlist", json={"rows": symbols})
                self.assertEqual(response.status_code, 400)
            unauthorized = self.request("PUT", "/options/api/watchlist", json={"rows": []})
            self.assertEqual(unauthorized.status_code, 401)

    def test_empty_shared_watchlist_stays_empty(self):
        with patch.dict(os.environ, {"RHTC_WATCHLIST_ADMIN_TOKEN": ""}, clear=False):
            response = self.request("PUT", "/options/api/watchlist", json={"rows": []})
            reloaded = self.request("GET", "/options/api/watchlist")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(reloaded.json()["rows"], [])
        self.assertEqual(reloaded.json()["count"], 0)

    def test_stock_quote_returns_tradier_fields_and_demo_fallback(self):
        self.assertEqual(parse_finnhub_metrics({"marketCapitalization": 148000, "shareOutstanding": 500}, {"metric": {"peTTM": 17.25, "epsTTM": 3.5, "netMarginTTM": 0.2, "revenuePerShareTTM": 40}}), {"market_cap": 148000000000.0, "price_earnings_ratio": 17.25, "earnings_per_share": 3.5, "profit_margin": 20.0, "revenue": 20000000000.0, "shares_outstanding": 500000000.0, "total_debt_to_capital": None, "institutional_ownership": None})
        self.assertEqual(parse_finnhub_metrics({}, {"metric": {}}), {"market_cap": None, "price_earnings_ratio": None, "earnings_per_share": None, "profit_margin": None, "revenue": None, "shares_outstanding": None, "total_debt_to_capital": None, "institutional_ownership": None})
        metrics = parse_finnhub_metrics(
            {"shareOutstanding": 500},
            {"metric": {"totalDebt/totalCapitalQuarterly": 0.42}},
            {"ownership": [
                {"name": "Fund A", "filingDate": "2025-12-31", "share": 100000000},
                {"name": "Fund A", "filingDate": "2024-12-31", "share": 90000000},
                {"name": "Fund B", "filingDate": "2025-09-30", "share": 50000000},
            ]},
        )
        self.assertEqual(metrics["shares_outstanding"], 500000000)
        self.assertEqual(metrics["total_debt_to_capital"], 42)
        self.assertEqual(metrics["institutional_ownership"], 30)
        profile = parse_finnhub_company_overview({"name": "Cloudflare Inc", "country": "US", "finnhubIndustry": "Technology", "ipo": "2019-09-13", "weburl": "https://www.cloudflare.com"}, {"description": "Cloudflare helps build a better Internet.", "city": "San Francisco", "state": "California"})
        self.assertEqual(profile["description"], "Cloudflare helps build a better Internet.")
        self.assertEqual(profile["industry"], "Technology")
        self.assertEqual(profile["city"], "San Francisco")
        self.assertEqual(profile["state"], "California")
        self.assertEqual(profile["country"], "US")
        self.assertEqual(profile["ipo"], "2019-09-13")
        async def provider_get(provider, path, params):
            self.assertEqual(params, {"symbols": "MU"})
            self.assertEqual(path, "/markets/quotes")
            return {"quotes": {"quote": {
                "symbol": "MU", "description": "Micron Technology, Inc.", "last": 128.5,
                "change": 1.25, "change_percentage": 0.98, "bid": 128.4, "ask": 128.6,
                "volume": 123456, "average_volume": 200000, "open": 127.0, "high": 130.0,
                "low": 126.5, "week_52_high": 165.0, "week_52_low": 84.5,
                "prevclose": 127.25, "trade_date": 1780000000000,
            }}}
        async def provider_metrics(provider, symbol):
            self.assertEqual(symbol, "MU")
            return {"market_cap": 148000000000.0, "price_earnings_ratio": 17.25, "earnings_per_share": 3.5, "profit_margin": 20.0, "revenue": 20000000000.0, "shares_outstanding": 500000000.0, "total_debt_to_capital": 42.0, "institutional_ownership": 30.0}

        with patch.dict(os.environ, {"TRADIER_API_TOKEN": "test-token"}, clear=True), patch.object(Tradier, "get", provider_get), patch.object(Tradier, "company_metrics", provider_metrics):
            response = self.request("GET", "/options/api/quote/MU")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["description"], "Micron Technology, Inc.")
        self.assertEqual(data["price"], 128.5)
        self.assertEqual(data["change_pct"], 0.98)
        self.assertEqual(data["previous_close"], 127.25)
        self.assertEqual(data["week_52_high"], 165.0)
        self.assertEqual(data["week_52_low"], 84.5)
        self.assertEqual(data["market_cap"], 148000000000.0)
        self.assertEqual(data["price_earnings_ratio"], 17.25)
        self.assertEqual(data["earnings_per_share"], 3.5)
        self.assertEqual(data["profit_margin"], 20.0)
        self.assertEqual(data["revenue"], 20000000000.0)
        self.assertEqual(data["shares_outstanding"], 500000000.0)
        self.assertEqual(data["total_debt_to_capital"], 42.0)
        self.assertEqual(data["institutional_ownership"], 30.0)
        self.assertEqual(data["source"], "tradier_sandbox")
        with patch.dict(os.environ, {}, clear=True):
            demo = self.request("GET", "/options/api/quote/MU")
        self.assertEqual(demo.status_code, 200)
        self.assertEqual(demo.json()["source"], "demo")
        self.assertIsNone(demo.json()["bid"])
        self.assertIsNone(demo.json()["market_cap"])
        self.assertIsNone(demo.json()["price_earnings_ratio"])
        self.assertIsNone(demo.json()["earnings_per_share"])
        self.assertIsNone(demo.json()["profit_margin"])
        self.assertIsNone(demo.json()["revenue"])
        self.assertIsNone(demo.json()["shares_outstanding"])
        self.assertIsNone(demo.json()["total_debt_to_capital"])
        self.assertIsNone(demo.json()["institutional_ownership"])
        self.assertEqual(self.request("GET", "/options/api/quote/bad!").status_code, 404)

    def test_tradier_selection_and_error_rows(self):
        expiries = [(date.today() + timedelta(days=days)).isoformat() for days in (3, 10, 17, 22)]
        async def provider_get(provider, path, params):
            if path.endswith("/quotes"):
                return {"quotes": {"quote": {"last": 100, "change": 1.25, "change_percentage": 1.27}}}
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
        self.assertEqual(data["rows"][0]["change"], 1.25)
        self.assertEqual(data["rows"][0]["change_pct"], 1.27)
        self.assertEqual(data["rows"][0]["contract"], f"{expiries[0].replace('-', '')}-105.0")

        with patch.dict(os.environ, {"TRADIER_API_TOKEN": "test-token"}, clear=True), patch.object(Tradier, "get", provider_get):
            expanded = self.request("GET", "/options/api/opportunities?limit=127").json()
        self.assertEqual(expanded["count"], 127)

        async def failing_get(provider, path, params):
            raise httpx.ConnectError("provider offline")
        with patch.dict(os.environ, {"TRADIER_API_TOKEN": "test-token"}, clear=True), patch.object(Tradier, "get", failing_get):
            data = self.request("GET", "/options/api/opportunities?limit=1").json()
        self.assertEqual(data["rows"][0]["source"], "error")
        self.assertNotIn("premium_yield", data["rows"][0])

    def test_contract_label_strips_unneeded_strike_zeros_and_keeps_decimal(self):
        self.assertEqual(format_option_contract("2026-09-05", 105), "20260905-105.0")
        self.assertEqual(format_option_contract("2026-09-05", "105.500"), "20260905-105.5")
        self.assertEqual(format_option_contract("2026-09-05", "105.250"), "20260905-105.25")

    def test_chain_pages_through_four_expiration_sets(self):
        expiries = [(date.today() + timedelta(days=days)).isoformat() for days in (2, 5, 10, 17, 22)]

        async def provider_get(provider, path, params):
            if path.endswith("/quotes"):
                return {"quotes": {"quote": {"last": 100, "change_percentage": 1, "description": "Micron Technology, Inc."}}}
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
        self.assertEqual(data["description"], "Micron Technology, Inc.")
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
