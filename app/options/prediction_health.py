"""Prediction infrastructure health: no paid inference or writes to research reports."""
import asyncio
import json
import os
import shutil
import logging
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
import httpx
from app.options import prediction_markets as pm

log = logging.getLogger(__name__)

def check(name, state, detail):
    return {"name":name,"state":state,"detail":str(detail)}

def age_hours(stamp):
    try:
        return (datetime.now(timezone.utc)-datetime.fromisoformat(stamp)).total_seconds()/3600
    except (ValueError,TypeError):
        return None

def save(result):
    with closing(pm.connect()) as db, db:
        db.execute("CREATE TABLE IF NOT EXISTS prediction_health (stamp TEXT PRIMARY KEY,payload TEXT NOT NULL)")
        db.execute("INSERT OR REPLACE INTO prediction_health VALUES (?,?)",(result["checked_at"],json.dumps(result)))
        db.execute("DELETE FROM prediction_health WHERE stamp NOT IN (SELECT stamp FROM prediction_health ORDER BY stamp DESC LIMIT 168)")

def latest_health():
    try:
        with closing(pm.connect()) as db:
            db.execute("CREATE TABLE IF NOT EXISTS prediction_health (stamp TEXT PRIMARY KEY,payload TEXT NOT NULL)")
            row=db.execute("SELECT payload FROM prediction_health ORDER BY stamp DESC LIMIT 1").fetchone()
        result=json.loads(row[0]) if row else {"state":"pending","checks":[]}
        age=age_hours(result.get("checked_at"))
        result["stale"]=age is None or age>2
        return result
    except Exception:
        log.exception("Prediction health read failed")
        return {"state":"unavailable","checks":[]}

def storage_checks():
    from app.options.api import watchlist_db_path
    checks=[]
    path=watchlist_db_path().with_name("rhtc_prediction_markets.sqlite3")
    with closing(pm.connect()) as db:
        scan=db.execute("SELECT stamp,count FROM scans ORDER BY stamp DESC LIMIT 1").fetchone()
        actual=db.execute("SELECT COUNT(*) FROM snapshots WHERE stamp=?",(scan["stamp"],)).fetchone()[0] if scan else 0
        reviewed=db.execute("SELECT COUNT(DISTINCT id) FROM market_research").fetchone()[0]
        checkpoint=db.execute("SELECT * FROM scan_checkpoint WHERE id=1").fetchone()
        # Validate the published snapshot count without scanning the entire database.
        checks.append(check("Completed snapshot integrity","pass" if scan and actual==scan["count"] else "fail" if scan else "pending",f"{actual} persisted markets" if scan else "No completed scan"))
        age=age_hours(scan["stamp"]) if scan else None
        checks.append(check("Completed snapshot freshness","pass" if age is not None and age<=12 else "warn" if scan else "pending",f"{age:.1f} hours since scan start" if age is not None else "Awaiting complete scan"))
        checks.append(check("Checkpoint recovery","pass" if checkpoint else "info",f"Saved cursor after {checkpoint['pages']} pages; recovery not crash-tested" if checkpoint else "No pending checkpoint"))
    status=pm.read_status()
    state=status.get("state")
    checks.append(check("Discovery worker","fail" if state=="failed" else "warn" if state=="interrupted" else "pass" if state=="completed" or state=="running" and pm.lock.locked() else "pending",f"{state}; {status.get('discovered',0)} retrieved; {status.get('error','')}"))
    rs=pm.read_research_status()
    state=rs.get("state")
    checks.append(check("Semantic worker","fail" if state=="failed" else "warn" if state in ("disabled","budget limited","retrying","cycle completed with retries") else "pass" if reviewed and state in ("running","cycle completed","up to date") else "pending",f"{state}; {reviewed} distinct cached market IDs (all snapshots); {rs.get('reason','')}"))
    usage=pm.daily_usage()
    checks.append(check("AI usage accounting","warn" if usage["unknown_usage"] else "pass",f"{usage['requests']}/{usage['request_limit']} requests; {usage['input_tokens']+usage['output_tokens']}/{usage['token_limit']} tokens; {usage['unknown_usage']} unknown requests"))
    disk=shutil.disk_usage(path.parent)
    db_bytes=sum(p.stat().st_size for p in (path,Path(str(path)+"-wal"),Path(str(path)+"-shm")) if p.exists())
    used=1-disk.free/disk.total
    checks.append(check("Persistent volume headroom","fail" if used>=.85 else "warn" if used>=.70 else "pass",f"Filesystem {used:.1%} used; prediction database and sidecars {db_bytes/1048576:.1f} MiB; filesystem free {disk.free/1048576:.1f} MiB"))
    return checks

async def provider_check():
    async with httpx.AsyncClient(timeout=20) as client:
        first,cursor=await pm.fetch_page(client,None)
        if not first or not cursor:
            raise ValueError("Provider returned no first page or cursor")
        second,_=await pm.fetch_page(client,cursor)
        if not second or not {str(m["id"]) for m in first}.isdisjoint({str(m["id"]) for m in second}):
            raise ValueError("Second page missing or overlaps first page")
        row=pm.normalize(first[0])
        return check("Live provider → normalization","pass",f"Two distinct pages retrieved; normalized market ID {row['id']}")

def synthetic_check():
    row=pm.normalize({"id":"audit-fixture","question":"AI chip supply","outcomes":["Yes","No"],"outcomePrices":["0.6","0.4"]})
    response=SimpleNamespace(status="completed",output_text=json.dumps({"items":[{"id":"audit-fixture","relevance":8,"topics":["AI/I"],"tickers":["TEST"]}]}))
    records=pm.validated_batch_items(response,[row])
    if len(records)!=1 or "json" not in pm.semantic_input([row]).lower():
        raise ValueError("Semantic contract mismatch")
    row["research"]=json.loads(records[0][2])
    mapped=pm.map_portfolio([row],[{"symbol":"TEST","peak":"AI/I","account":"Synthetic","quantity":100}])[0]
    if mapped["watchlist_matches"]!=["TEST"] or not mapped["holdings"] or mapped["probabilities"].get("Yes")!=.6:
        raise ValueError("Synthetic portfolio mapping mismatch")
    return check("Synthetic pipeline → portfolio mapping","pass","Normalization, JSON request/response contract, candidate mapping; no live AI request or production report written")

def integration_checks():
    # Inspect actual deployed functions; do not confuse wiring with model execution.
    import inspect
    from app.options import api, news, long_game, forward_intelligence
    checks=[]
    for label,fn,markers in [
        ("News Summary",news._build_news_summary,["research_context","prediction_context"]),
        ("The Long Game",api.generate_long_game_analysis,["research_context","prediction_market_evidence"]),
        ("Stock Analysis",api.analyze_stock,["ticker_context","prediction"]),
        ("Buffett Model",api.buffett_screen,["ticker_context","prediction_market_context"]),
        ("CEO Risk",api.assess_ceo_risk,["ticker_context","prediction_market_context"]),
        ("Covered Call Analysis",api.analyze_symbol,["ticker_context","expiry"]),
    ]:
        source=inspect.getsource(fn)
        checks.append(check(label+" wiring","pass" if all(m in source for m in markers) else "fail","Deployed source inspected; live model inference not exercised"))
    context=pm.research_context()
    checks.append(check("Completed evidence → report context","pass" if context.get("selected") and not context.get("stale") else "pending",f"{len(context.get('selected',[]))} selected records; {context.get('status','stale' if context.get('stale') else 'available')}"))
    return checks

async def run_health():
    checks=[]
    for name,fn in [("Storage and worker checks",storage_checks),("Synthetic integration",synthetic_check),("Model integrations",integration_checks)]:
        try:
            value=await asyncio.to_thread(fn)
            checks.extend(value if isinstance(value,list) else [value])
        except Exception as exc:
            checks.append(check(name,"fail",type(exc).__name__))
            log.exception("Prediction health check failed: %s",name)
    try:
        checks.append(await provider_check())
    except Exception as exc:
        checks.append(check("Live provider → normalization","fail",type(exc).__name__))
    state="fail" if any(c["state"]=="fail" for c in checks) else "warn" if any(c["state"] in ("warn","pending") for c in checks) else "pass"
    result={"checked_at":datetime.now(timezone.utc).isoformat(),"state":state,"checks":checks,"scope":"Live provider and stored data checks, synthetic pipeline and deployed wiring; no paid model inference."}
    await asyncio.to_thread(save,result)
    log.warning("Prediction infrastructure health: %s (%d checks)",state,len(checks))
    return result

async def scheduler():
    while True:
        try:
            await run_health()
        except Exception:
            log.exception("Prediction infrastructure health cycle failed")
        await asyncio.sleep(3600)
