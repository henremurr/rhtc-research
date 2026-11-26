from app.options.uncertainty_pdf import normalize_pdf_text


def test_uncertainty_pdf_typography():
    source = "10\u2011Q / 8\u2011K; AI\u2011cloud; 100\u202fshares; \u221212%; \u2265 5\nNext paragraph"
    expected = "10-Q / 8-K; AI-cloud; 100 shares; -12%; >= 5\nNext paragraph"
    assert normalize_pdf_text(source) == expected


def test_uncertainty_pdf_preserves_supported_punctuation():
    text = "RHTC — ‘opinion’ – 75% • $30,000"
    assert normalize_pdf_text(text) == text
