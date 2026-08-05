from fastapi import FastAPI
from pydantic import BaseModel
import os
import httpx

app = FastAPI(
    title="RHTC Research API",
    version="0.2.0"
)

PERPLEXITY_API_KEY = os.getenv("PERPLEXITY_API_KEY")

class BatchItem(BaseModel):
    id: str
    url: str
    instructions: str

class BatchRequest(BaseModel):
    items: list[BatchItem]

@app.get("/")
def root():
    return {"status": "running"}

@app.get("/health")
def health():
    return {
        "status": "running",
        "perplexity_api_key": "configured" if PERPLEXITY_API_KEY else "missing"
    }

@app.post("/batch-analyze")
async def batch_analyze(request: BatchRequest):

    if not PERPLEXITY_API_KEY:
        return {"error": "PERPLEXITY_API_KEY missing"}

    headers = {
        "Authorization": f"Bearer {PERPLEXITY_API_KEY}",
        "Content-Type": "application/json"
    }

    results = []

    async with httpx.AsyncClient(timeout=180) as client:

        for item in request.items:

            prompt = f"""
Analyze this article.

URL:
{item.url}

Instructions:
{item.instructions}

Return:

• Executive Summary

• Key Facts

• Strategic Significance

• Bullish Implications

• Bearish Risks

• Portfolio Implications

• Sources
"""

            payload = {
                "model": "sonar",
                "messages": [
                    {
                        "role": "system",
                        "content": "You are an institutional equity research analyst."
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ]
            }

            response = await client.post(
                "https://api.perplexity.ai/chat/completions",
                headers=headers,
                json=payload
            )

            if response.status_code != 200:
                results.append({
                    "id": item.id,
                    "error": response.text
                })
                continue

            data = response.json()

            results.append({
                "id": item.id,
                "url": item.url,
                "analysis": data["choices"][0]["message"]["content"]
            })

    return {
        "count": len(results),
        "results": results
    }
