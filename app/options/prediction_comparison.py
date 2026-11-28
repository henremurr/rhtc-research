"""Conservative cross-provider comparison; never infer equivalence from titles alone."""
import math
from datetime import datetime, timezone
from collections import defaultdict


def canonical(value):
    return " ".join(str(value or "").split()).casefold()


def timestamp(value):
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return dt.astimezone(timezone.utc) if dt.tzinfo else None
    except (ValueError, TypeError):
        return None


def key(row):
    title = canonical(row.get("title"))
    rules = canonical(row.get("description"))
    end = timestamp(row.get("end_date"))
    # Exact normalized full rules and deadline are mandatory; no fuzzy matching.
    if not title or not rules or not end:
        return None
    return title, rules, end


def yes(row):
    value = next((v for k, v in row.get("probabilities", {}).items() if k.casefold() == "yes"), None)
    return value if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and 0 <= value <= 1 else None


def compare(rows):
    groups = defaultdict(list)
    for row in rows:
        match = key(row)
        if match:
            groups[match].append(row)
    result = []
    for group in groups.values():
        a = [r for r in group if r.get("provider", "polymarket") == "polymarket"]
        b = [r for r in group if r.get("provider") == "kalshi"]
        # Ambiguous duplicate groups cannot establish a unique comparison.
        if len(a) != 1 or len(b) != 1:
            continue
        p, k = a[0], b[0]
        x, y = yes(p), yes(k)
        t1 = timestamp(p.get("observed_at"))
        t2 = timestamp(k.get("observed_at"))
        if x is None or y is None or t1 is None or t2 is None or abs((t1-t2).total_seconds()) > 3600:
            continue
        delta = round((y-x)*100, 2)
        result.append({"polymarket_id": p["id"], "kalshi_id": k["id"],
                       "kalshi_minus_polymarket_pp": delta,
                       "classification": "agreement" if abs(delta) <= 5 else "divergence" if abs(delta) >= 10 else "intermediate",
                       "match_basis": "exact normalized title, full rules and deadline; observations within one hour",
                       "warning": "Candidate equivalence only; not independent factual corroboration or a score multiplier."})
    return result
