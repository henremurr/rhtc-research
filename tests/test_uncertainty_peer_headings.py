from app.options.uncertainty_pdf import narrative_blocks

def test_inferred_colon_headings_are_peers():
    source = """## Executive investment opinion
Holdings: what to retain and why. Retain core defense primes.
Holdings: what to reduce and why. Reduce or trim speculative positions.
Holdings: what to build and on what conditional evidence. Build selectively.
Overarching posture: defensive, selective, staged. Preserve core holdings.
"""
    headings = [(kind, line) for kind, line in narrative_blocks(source) if kind in ("subsection", "minor")]
    assert headings == [
        ("subsection", "Holdings: what to retain and why"),
        ("subsection", "Holdings: what to reduce and why"),
        ("subsection", "Holdings: what to build and on what conditional evidence"),
        ("subsection", "Overarching posture: defensive, selective, staged"),
    ]

def test_explicit_nesting_is_preserved():
    assert list(narrative_blocks("## Major\n### Topic\n#### Supporting detail\nNarrative.")) == [
        ("section", "Major"), ("subsection", "Topic"), ("minor", "Supporting detail"), ("body", "Narrative.")
    ]

def test_dimension_supporting_headings_remain_nested():
    source = "## Seven dimensions of structural uncertainty\nTechnological uncertainty — Overview\nRisk drivers: what to monitor. Monitor execution.\n## Peak 1"
    assert ("minor", "Risk drivers: what to monitor") in list(narrative_blocks(source))
