from app.options.uncertainty_pdf import list_levels, narrative_blocks

def test_legacy_numbered_children():
    text = "- Across both accounts, consider the following action hierarchy:\n\n1. Wait and reconcile.\n\n2. Require disclosure.\n3. Recompute dilution.\n- Do not build now."
    assert list(list_levels(text).values()) == [0, 1, 1, 1, 0]
    assert [kind for kind, _ in narrative_blocks(text)] == ["list:0", "list:1", "list:1", "list:1", "list:0"]

def test_explicit_nested_lists():
    text = "- Parent\n    1. Child\n        - Grandchild\n    2. Child\n- Sibling\n\nStandalone paragraph.\n1. Independent item"
    assert list(list_levels(text).values()) == [0, 1, 2, 1, 0, 0]

def test_independent_ordered_list():
    assert list(list_levels("- Ordinary bullet.\n1. Independent item\n2. Another").values()) == [0, 0, 0]
