from __future__ import annotations

import asyncio
import json
import os
from typing import Any

import httpx

from app.models import BatchItem


PERPLEXITY_URL = "https://api.perplexity.ai/v1/sonar"


def _extract_json_block(text: str) -> dict[str, Any] | None:
    candidates = [text]
    if "```json" in text:
        candidates.append(text.split("```json", 1)[1].split("```", 1)[0])
    elif "```" in text:
        candidates.append(text.split("```", 1)[1].split("```", 1)[0])

    for candidate in candidates:
        try:
            return json.loads(candidate.strip())
        except json.JSONDecodeError:
            continue
    return None


async def analyze_one(
    client: httpx.AsyncClient,
    item: BatchItem,
    model: str,
    semaphore: asyncio.Semaphore,
) -> dict[str, Any]:
    api_key = os.getenv("PERPLEXITY_API_KEY")
    if not api_key:
        raise RuntimeError("PERPLEXITY_API_KEY is not configured")

    prompt = f"""
Analyze this source for the Rocking Horse Trading Co. Three Peaks framework.

URL:
{item.url}

User instructions:
{item.instructions}

Return a single valid JSON object with these fields:
headline: string
summary: string
pillar: one of "AI/I", "EFM/I", "DS/I", "Cross-Peak", "Other"
materiality_tier: 1, 2, or 3
assessment: one of "very bullish", "bullish", "moderately bullish", "neutral", "bearish", "very bearish"
affected_symbols: array of ticker symbols
key_facts: array of concise strings
strategic_significance: array of concise strings
risks: array of concise strings

Rules:
- Distinguish reported facts from interpretation.
- Do not invent figures.
- Include citations in the prose answer when supported.
- Keep the summary decision-focused and suitable for an executive report.
""".strip()

    payload = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are a disciplined institutional investment research analyst. "
                    "Use current web-grounded evidence and return valid JSON."
                ),
            },
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.1,
    }

    async with semaphore:
        for attempt in range(4):
            response = await client.post(
                PERPLEXITY_URL,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )

            if response.status_code == 429:
                await asyncio.sleep(2 ** attempt)
                continue

            if response.status_code >= 400:
                raise RuntimeError(
                    f"Perplexity HTTP {response.status_code}: {response.text[:500]}"
                )

            data = response.json()
            content = data["choices"][0]["message"]["content"]
            parsed = _extract_json_block(content)

            return {
                "id": item.id,
                "url": str(item.url),
                "raw_analysis": content,
                "parsed": parsed,
                "citations": data.get("citations", []),
                "usage": data.get("usage", {}),
            }

    raise RuntimeError("Perplexity rate limit persisted after retries")
