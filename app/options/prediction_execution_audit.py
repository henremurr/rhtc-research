"""Offline execution canary. Run only in a dedicated subprocess with temporary data."""
import asyncio
import json
import os
import tempfile
from contextlib import closing, ExitStack
from datetime import datetime, timezone, timedelta
from types import SimpleNamespace
from unittest.mock import patch, AsyncMock

async def run():
    now=datetime.now(timezone.utc)
    expiry=(now.date()+timedelta(days=7)).isoformat()
    marker="RHTC_EXECUTION_FIXTURE"
    url="https://example.com/fixture"
    event={"id":"fixture","title":marker,"association":"candidate ticker","quality":"higher liquidity",
           "research":{"relevance":10},"changes_pp":{"1":{"Yes":20}},"end_date":expiry}
    context={"status":"available","as_of":now.isoformat(),"selected":[event]}
    results=[]
    def record(name,ok,detail):
        results.append({"name":name+" execution (fixture)","state":"pass" if ok else "fail","detail":detail})
    with tempfile.TemporaryDirectory(prefix="rhtc-execution-") as folder, ExitStack() as stack:
        stack.enter_context(patch.dict(os.environ,{"RHTC_DATA_DIR":folder,"OPENAI_API_KEY":"fixture-not-a-real-key"}))
        from app.options import api, news, prediction_markets as pm, forward_intelligence as fi
        from app.options.long_game import analyze_long_game
        # Fail closed if a future model path attempts an unmocked HTTP request.
        stack.enter_context(patch("httpx.AsyncClient.send",new=AsyncMock(side_effect=RuntimeError("Network disabled in execution fixture"))))
        stack.enter_context(patch("httpx.Client.send",side_effect=RuntimeError("Network disabled in execution fixture")))
        stack.enter_context(patch.object(api,"require_watchlist_storage",lambda:None))
        stack.enter_context(patch.object(fi,"ticker_context",return_value=context))
        stack.enter_context(patch.object(pm,"research_context",return_value=context))
        stack.enter_context(patch.object(api,"fetch_saved_stock_sources",new=AsyncMock(return_value=([],[]))))
        stack.enter_context(patch.object(api,"fetch_sec_company_facts",new=AsyncMock(return_value={"status":"unavailable"})))
        stack.enter_context(patch.object(api,"fetch_buffett_finnhub_data",new=AsyncMock(return_value={"status":"unavailable"})))
        with closing(api.connect_watchlist_db()) as db, db:
            db.execute("DELETE FROM symbols")
            db.execute("INSERT INTO symbols(position,symbol,peak,quantity) VALUES (1,'TEST','AI/I',100)")
        with closing(news.connect_db()) as db, db:
            db.execute("INSERT INTO news_items(url,title,source,first_seen_at,last_seen_at,snippet) VALUES (?,?,?,?,?,?)",
                       (url,"Fixture story","Fixture",now.isoformat(),now.isoformat(),"Synthetic research evidence"))
        candidate={"market_id":"fixture","source_url":url,"direction":"positive","rationale":"Fixture evidence",
                   "corroborated":True,"already_reflected":False,"economic_impact":1,"corroboration":1}
        citation=SimpleNamespace(type="url_citation",url_citation=SimpleNamespace(url=url,title="Fixture"))
        outputs={
            "Stock Analysis":"## Summary and rating\n**Rating: 4 — Grow**\nFixture summary.\n## Detailed analysis\nFixture details.\nFIS_CANDIDATE:"+json.dumps(candidate),
            "Covered Call Analysis":"## Covered-call verdict\nMixed\nScorecard — Income: 3/5 · Upside cushion: 3/5 · Event risk: 3/5 · Liquidity: 3/5",
            "CEO Risk":json.dumps({"company_name":"Fixture","ceo_name":"Fixture","as_of":now.isoformat(),"confidence":80,"summary":"Fixture","factors":[{"id":i,"name":str(i),"risk_score":2,"evidence":"Fixture"} for i in range(1,7)],"scenarios":[],"monitor_signals":[]}),
            "Buffett Model":json.dumps({"criteria":[{"id":i,"score":0,"evidence":"Unknown"} for i in range(1,14)],"metrics":{}}),
            "News Summary":"## Trading desk — 60-second read\nFixture synthesis [S0001].",
            "The Long Game":"Fixture strategy with independent corroboration required.",
        }
        active=""
        calls=[]
        async def create(**kwargs):
            calls.append(kwargs)
            if marker not in str(kwargs.get("input","")):
                raise AssertionError("Prediction context missing from provider input")
            return SimpleNamespace(output_text=outputs[active],status="completed",output=[SimpleNamespace(content=[SimpleNamespace(annotations=[citation])])])
        client=SimpleNamespace(responses=SimpleNamespace(create=create))
        stack.enter_context(patch("openai.AsyncOpenAI",return_value=client))
        async def execute(name,fn,validate):
            nonlocal active
            active=name
            calls.clear()
            try:
                result=await fn()
                if not calls or not validate(result):
                    raise AssertionError("Output or persistence contract mismatch")
                record(name,True,"Actual workflow executed; fixture provider input and output validated")
            except Exception as exc:
                record(name,False,str(exc)[:300])
        await execute("Stock Analysis",lambda:api.analyze_stock(api.StockAnalysisInput(symbol="TEST")),
                      lambda r:r.get("rating")==4 and r.get("forward_intelligence",{}).get("fis") is not None and "TEST" in fi.latest_fis())
        await execute("Covered Call Analysis",lambda:api.analyze_symbol(api.SymbolAnalysisInput(symbol="TEST",screen={"expiry":expiry})),
                      lambda r:r.get("total_score")==3 and fi.ticker_context.call_args.args[-1]==expiry)
        await execute("CEO Risk",lambda:api.assess_ceo_risk(api.BuffettScreenInput(symbol="TEST")),
                      lambda r:r.get("risk_score")==50 and r.get("report_count")==1)
        await execute("Buffett Model",lambda:api.buffett_screen(api.BuffettScreenInput(symbol="TEST")),
                      lambda r:r.get("criteria_total")==13 and r.get("score_percent")==0 and r.get("report_count")==1)
        await execute("News Summary",lambda:news._build_news_summary(news.NewsSummaryInput(urls=[url])),
                      lambda r:r.get("story_count")==1 and bool(r.get("analysis")))
        checkpoint={}
        await execute("The Long Game",lambda:analyze_long_game(client,"fixture",{"positions":[],"prediction_market_evidence":context},{},{},[],now.isoformat(),lambda x:None,checkpoint,lambda k,v:None,str),
                      lambda r:r[1]==0 and len(checkpoint)>=3 and "## Strategy" in r[0])
        try:
            assessment=fi.latest_fis()["TEST"]
            approved=fi.review_fis("TEST",assessment["report_id"],True,"Synthetic independent review")
            ok=fi.composite_score(4,3,approved)==7.25 and fi.composite_score(4,3,fi.review_fis("TEST",assessment["report_id"],False,"Rejected"))==7
            record("Composite Score",ok,"Persistent review, approval and rejection executed")
        except Exception as exc:
            record("Composite Score",False,str(exc)[:300])
    return results

if __name__=="__main__":
    results=asyncio.run(run())
    print(json.dumps(results))
    raise SystemExit(0 if len(results)==7 and all(r["state"]=="pass" for r in results) else 1)
