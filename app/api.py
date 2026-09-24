from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from typing import Any

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse

from app.models import BatchRequest
from app.options.api import app as options_app
from app.perplexity_client import analyze_one
from app.reporting import create_pdf
from app.three_peaks import (
    classify_pillar,
    extract_symbols,
    infer_assessment,
    infer_materiality,
)


app = FastAPI(
    title="RHTC Research API",
    version="1.0.0",
    description="Three Peaks batch research, classification, and PDF reporting.",
)
app.mount("/options", options_app)

HOLDINGS_PATH = Path("config/holdings.json")
REPORT_DIR = Path("reports")


def load_holdings() -> dict[str, list[str]]:
    if HOLDINGS_PATH.exists():
        return json.loads(HOLDINGS_PATH.read_text(encoding="utf-8"))
    return {"AI/I": [], "EFM/I": [], "DS/I": [], "Other": []}


@app.get("/")
async def root() -> dict[str, str]:
    return {"status": "running", "service": "RHTC Research API", "version": "1.0.0"}


@app.get("/health")
async def health() -> dict[str, str]:
    return {
        "status": "running",
        "perplexity_api_key": (
            "configured" if os.getenv("PERPLEXITY_API_KEY") else "missing"
        ),
    }


@app.get("/holdings")
async def holdings() -> dict[str, list[str]]:
    return load_holdings()


@app.post("/batch-analyze")
async def batch_analyze(request: BatchRequest) -> dict[str, Any]:
    if not os.getenv("PERPLEXITY_API_KEY"):
        raise HTTPException(
            status_code=500,
            detail="PERPLEXITY_API_KEY is not configured in Railway",
        )

    semaphore = asyncio.Semaphore(request.concurrency)
    async with httpx.AsyncClient(timeout=240.0) as client:
        results = await asyncio.gather(
            *[
                analyze_one(client, item, request.model, semaphore)
                for item in request.items
            ],
            return_exceptions=True,
        )

    holdings_data = load_holdings()
    completed: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []

    for item, result in zip(request.items, results):
        if isinstance(result, Exception):
            errors.append(
                {"id": item.id, "url": str(item.url), "error": str(result)}
            )
            continue

        parsed = result.get("parsed") or {}
        raw = result.get("raw_analysis", "")
        combined_text = json.dumps(parsed) + "\n" + raw

        record = {
            "id": item.id,
            "url": str(item.url),
            "headline": parsed.get("headline", ""),
            "summary": parsed.get("summary", raw),
            "pillar": parsed.get("pillar") or classify_pillar(combined_text),
            "materiality_tier": parsed.get("materiality_tier")
            or infer_materiality(combined_text),
            "assessment": parsed.get("assessment")
            or infer_assessment(combined_text),
            "affected_symbols": parsed.get("affected_symbols")
            or extract_symbols(combined_text, holdings_data),
            "key_facts": parsed.get("key_facts", []),
            "strategic_significance": parsed.get("strategic_significance", []),
            "risks": parsed.get("risks", []),
            "citations": result.get("citations", []),
            "usage": result.get("usage", {}),
        }
        completed.append(record)

    pdf_url = None
    if request.create_pdf and completed:
        report_path = create_pdf(request.report_title, completed, REPORT_DIR)
        pdf_url = f"/reports/{report_path.name}"

    return {
        "requested": len(request.items),
        "completed": len(completed),
        "failed": len(errors),
        "results": completed,
        "errors": errors,
        "pdf_url": pdf_url,
    }


@app.get("/reports/{filename}")
async def download_report(filename: str):
    safe_name = Path(filename).name
    path = REPORT_DIR / safe_name
    if not path.exists():
        raise HTTPException(status_code=404, detail="Report not found")
    return FileResponse(path, media_type="application/pdf", filename=safe_name)
