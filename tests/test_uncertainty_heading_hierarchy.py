from app.options.uncertainty_pdf import narrative_blocks, plain_subheading

def test_legacy_plain_topic_title():
    source = """## Peak 1 — AI and Infrastructure

AI value chain economics and the timing problem

AI deployment economics are governed by three linked flows: chip supply, rack integration and site realization.

Capital expenditure: scale, margin leverage and financing risk

AI infrastructure requires large capital investments and substantial financing.
"""
    blocks = list(narrative_blocks(source))
    assert ("subsection", "AI value chain economics and the timing problem") in blocks
    assert ("subsection", "Capital expenditure: scale, margin leverage and financing risk") in blocks
    assert not plain_subheading("The portfolio should retain cash.", True, "More narrative follows.")

def test_explicit_levels():
    assert list(narrative_blocks("## Major\n### Topic\n#### Detail\nNarrative.")) == [
        ("section", "Major"), ("subsection", "Topic"), ("minor", "Detail"), ("body", "Narrative.")
    ]
