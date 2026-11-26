from io import BytesIO
from pypdf import PdfReader
from app.options.uncertainty_pdf import build_uncertainty_pdf

def test_full_pdf_with_nested_lists_and_special_heading_characters():
    text = """## Executive investment opinion
### Risk & opportunity: thresholds < 5 and > 2
- Across both accounts, consider the following action hierarchy:

1. Wait and reconcile.
2. Require disclosure.
3. Recompute dilution.
- Do not build now.
#### Supporting detail
A narrative paragraph.
## Seven dimensions of structural uncertainty
Technological uncertainty — overview
Economic uncertainty — overview
Monetary and credit uncertainty — overview
Geopolitical uncertainty — overview
Energy and resource uncertainty — overview
Societal uncertainty — overview
Financial uncertainty — overview
## Peak 1
### AI value chain economics
Narrative.
"""
    pdf = PdfReader(BytesIO(build_uncertainty_pdf(text, "November 26, 2026")))
    all_text = "\n".join(page.extract_text() or "" for page in pdf.pages)
    assert "Table of Contents" in all_text
    assert "Risk & opportunity: thresholds < 5 and > 2" in all_text
    assert "Recompute dilution." in all_text
    assert "2.7 Financial Uncertainty" in all_text
    assert pdf.outline
