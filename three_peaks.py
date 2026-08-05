from __future__ import annotations

import re
from typing import Any


PILLAR_KEYWORDS = {
    "AI/I": {
        "ai", "artificial intelligence", "semiconductor", "memory", "hbm",
        "server", "data center", "cloud", "gpu", "networking", "optical",
        "software", "compute", "inference", "training",
    },
    "EFM/I": {
        "energy", "natural gas", "pipeline", "nuclear", "uranium", "fuel",
        "mineral", "scandium", "antimony", "grid", "power", "utility",
        "infrastructure", "reactor", "triso", "enrichment",
    },
    "DS/I": {
        "defense", "missile", "radar", "space", "satellite", "rocket",
        "air force", "navy", "army", "pentagon", "autonomous", "drone",
        "interceptor", "patriot", "sensor", "launch",
    },
}


def classify_pillar(text: str) -> str:
    lowered = text.lower()
    scores = {
        pillar: sum(1 for keyword in words if keyword in lowered)
        for pillar, words in PILLAR_KEYWORDS.items()
    }
    ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)

    if not ranked or ranked[0][1] == 0:
        return "Other"

    if len(ranked) > 1 and ranked[1][1] > 0 and ranked[0][1] - ranked[1][1] <= 1:
        return "Cross-Peak"

    return ranked[0][0]


def extract_symbols(text: str, holdings: dict[str, Any]) -> list[str]:
    found: list[str] = []
    upper = text.upper()
    for pillar_symbols in holdings.values():
        for symbol in pillar_symbols:
            if re.search(rf"(?<![A-Z]){re.escape(symbol)}(?![A-Z])", upper):
                found.append(symbol)
    return sorted(set(found))


def infer_assessment(text: str) -> str:
    lowered = text.lower()
    bullish = sum(lowered.count(term) for term in ["strongly bullish", "very bullish", "bullish", "positive"])
    bearish = sum(lowered.count(term) for term in ["strongly bearish", "very bearish", "bearish", "negative"])

    if bullish >= bearish + 3:
        return "very bullish"
    if bullish > bearish:
        return "bullish"
    if bearish >= bullish + 3:
        return "very bearish"
    if bearish > bullish:
        return "bearish"
    return "neutral"


def infer_materiality(text: str) -> int:
    lowered = text.lower()
    tier1_terms = [
        "transformative", "thesis-changing", "material contract",
        "record revenue", "strategic bottleneck", "multiyear",
    ]
    tier2_terms = [
        "important", "meaningful", "strategic confirmation",
        "operational milestone", "capacity expansion",
    ]
    if any(term in lowered for term in tier1_terms):
        return 1
    if any(term in lowered for term in tier2_terms):
        return 2
    return 3
