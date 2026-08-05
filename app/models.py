from typing import Literal

from pydantic import BaseModel, Field, HttpUrl


Pillar = Literal["AI/I", "EFM/I", "DS/I", "Cross-Peak", "Other"]
Assessment = Literal[
    "very bullish",
    "bullish",
    "moderately bullish",
    "neutral",
    "bearish",
    "very bearish",
]


class BatchItem(BaseModel):
    id: str = Field(min_length=1, max_length=100)
    url: HttpUrl
    instructions: str = Field(
        default=(
            "Produce a factual executive analysis with key facts, strategic "
            "significance, portfolio implications, risks, and citations."
        ),
        max_length=5000,
    )


class BatchRequest(BaseModel):
    items: list[BatchItem] = Field(min_length=1, max_length=25)
    model: str = "sonar-pro"
    concurrency: int = Field(default=4, ge=1, le=5)
    create_pdf: bool = False
    report_title: str = "RHTC Three Peaks Research Report"


class ArticleAnalysis(BaseModel):
    id: str
    url: str
    headline: str = ""
    summary: str
    pillar: Pillar = "Other"
    materiality_tier: int = Field(default=3, ge=1, le=3)
    assessment: Assessment = "neutral"
    affected_symbols: list[str] = []
    key_facts: list[str] = []
    strategic_significance: list[str] = []
    risks: list[str] = []
    citations: list[str] = []
