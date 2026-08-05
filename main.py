from fastapi import FastAPI
from pydantic import BaseModel, HttpUrl

app = FastAPI(title="RHTC Research API")


class BatchItem(BaseModel):
    id: str
    url: HttpUrl
    instructions: str = ""


class BatchRequest(BaseModel):
    items: list[BatchItem]


@app.get("/")
async def root():
    return {"status": "running"}


@app.post("/batch-analyze")
async def batch_analyze(request: BatchRequest):
    return {
        "status": "placeholder",
        "count": len(request.items),
        "results": [
            {
                "id": item.id,
                "url": str(item.url),
                "instructions": item.instructions,
                "status": "pending"
            }
            for item in request.items
        ]
    }
