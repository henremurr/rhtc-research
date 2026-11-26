from app.options.uncertainty_pdf import narrative_blocks, dimension_heading

def test_legacy_dimension_variants():
    sample = """## Seven dimensions of structural uncertainty
Technological uncertainty — What can change
2. **Macroeconomic uncertainty:** economic narrative
### Monetary policy (rates)
4) Geopolitical uncertainty — trade
**Energy and infrastructure:** power
### Social uncertainty: employment
7. Financial markets — funding
## Peak 1
"""
    headings = [line for kind, line in narrative_blocks(sample) if kind == "dimension"]
    assert headings == ["Technological uncertainty", "Economic uncertainty", "Monetary uncertainty", "Geopolitical uncertainty", "Energy uncertainty", "Societal uncertainty", "Financial uncertainty"]

def test_does_not_promote_prose():
    assert dimension_heading("Economic uncertainty is increasing.") is None

def test_missing_dimensions_are_disclosed():
    blocks = list(narrative_blocks("## Seven dimensions of structural uncertainty\nTechnological uncertainty — text\n## Peak 1"))
    assert any("Navigation note:" in line and "Economic" in line for kind, line in blocks)


def test_compound_headings_from_report_screenshots_and_variants():
    sample = """## Seven dimensions of structural uncertainty
Technological uncertainty — What can change
Economic (real-activity) uncertainty — Demand, capex cycles and revenue timing
Monetary and credit uncertainty — Funding availability, cost of capital, and financing structure
Geopolitical uncertainty — Export controls
Energy and resource uncertainty — Grid constraints, fuel supply and project financing
Societal and labor-market uncertainty — Employment
Financial and valuation uncertainty — Market liquidity
## Peak 1
"""
    blocks = list(narrative_blocks(sample))
    assert [line for kind, line in blocks if kind == "dimension"] == [
        "Technological uncertainty", "Economic uncertainty", "Monetary uncertainty",
        "Geopolitical uncertainty", "Energy uncertainty", "Societal uncertainty", "Financial uncertainty",
    ]
    assert not any("Navigation note:" in line for kind, line in blocks)
    assert any("Monetary and credit uncertainty" in line for kind, line in blocks if kind == "body")
    assert dimension_heading("Monetary uncertainty affects the cost and availability of leverage.") is None
