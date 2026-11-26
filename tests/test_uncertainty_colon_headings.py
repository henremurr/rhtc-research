from app.options.uncertainty_pdf import colon_heading, narrative_blocks

def test_colon_qualifiers_from_saved_report():
    examples = [
        ("Holdings: what to retain and why. Retain core defense primes.", "Holdings: what to retain and why", "Retain core defense primes."),
        ("Holdings: what to reduce and why. Reduce or trim speculative positions.", "Holdings: what to reduce and why", "Reduce or trim speculative positions."),
        ("Holdings: what to build and on what conditional evidence. Build selectively.", "Holdings: what to build and on what conditional evidence", "Build selectively."),
        ("Capital expenditure: scale, margin leverage and financing risk", "Capital expenditure: scale, margin leverage and financing risk", ""),
    ]
    for source, title, body in examples:
        assert colon_heading(source) == (title, body)
        blocks = list(narrative_blocks("## Example\n### Topic\n" + source))
        assert ("minor", title) in blocks or ("subsection", title) in blocks
        if body:
            assert ("body", body) in blocks

def test_ambiguous_colon_remains_inline():
    line = "Portfolio risk: The company is dependent on external financing."
    assert colon_heading(line) is None
    assert ("body", line) in list(narrative_blocks("## Example\n" + line))

def test_explicit_markdown_heading_preserves_colon():
    assert ("subsection", "Holdings: what to retain and why") in list(narrative_blocks("## Example\n### Holdings: what to retain and why\nRetain core defense primes."))
