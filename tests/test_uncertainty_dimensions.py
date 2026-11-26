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
