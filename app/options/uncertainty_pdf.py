"""Render a stored investment strategy report without calling the analysis provider."""
import re
from io import BytesIO
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.pdfgen.canvas import Canvas


def build_uncertainty_pdf(analysis, as_of):
    output = BytesIO()
    title = "Age of Structural Uncertainty"
    ink = colors.HexColor("#182229")
    gold = colors.HexColor("#C6A45C")
    width, height = letter
    doc = SimpleDocTemplate(output, pagesize=letter, leftMargin=48, rightMargin=48,
                            topMargin=82, bottomMargin=42, title=title, author="Rocking Horse Trading Co.")
    body = ParagraphStyle("Narrative", fontName="Helvetica", fontSize=10.5, leading=15,
                          spaceAfter=8, textColor=ink, splitLongWords=True)
    heading = ParagraphStyle("Section", parent=body, fontName="Helvetica-Bold",
                             fontSize=15, leading=19, spaceBefore=15, spaceAfter=8, keepWithNext=True)
    subheading = ParagraphStyle("Subsection", parent=heading, fontSize=12, leading=16)
    bullet = ParagraphStyle("List", parent=body, leftIndent=16, firstLineIndent=-12)
    logo = Path(__file__).parent / "static" / "apple-touch-icon.png"

    def decorate(canvas, document):
        canvas.saveState()
        canvas.drawImage(str(logo), 48, height-58, width=38, height=38, mask="auto")
        canvas.setFillColor(ink)
        canvas.setFont("Helvetica-Bold", 16)
        canvas.drawString(96, height-34, title)
        canvas.setFont("Helvetica", 9)
        canvas.drawString(96, height-49, str(as_of))
        canvas.setStrokeColor(gold)
        canvas.line(48, height-68, width-48, height-68)
        canvas.line(48, 34, width-48, 34)
        canvas.setFont("Helvetica", 8)
        canvas.drawString(48, 21, "RHTC | Rocking Horse Trading Co. | Three Peaks Research")
        canvas.drawRightString(width-48, 21, f"Page {document.page}")
        canvas.restoreState()

    def markup(line):
        parts = re.split(r"(\*\*[^*]+\*\*)", line)
        return "".join("<b>" + escape(p[2:-2]) + "</b>" if p.startswith("**") and p.endswith("**")
                       else escape(p) for p in parts)

    story = []
    for raw in analysis.splitlines():
        line = raw.strip()
        if not line:
            continue
        match = re.match(r"^(#{1,6})\s+(.+)", line)
        if match:
            story.append(Paragraph(markup(match.group(2)), heading if len(match.group(1)) <= 2 else subheading))
        elif re.match(r"^(?:[-*]|\d+\.)\s+", line):
            story.append(Paragraph(markup(line), bullet))
        else:
            story.append(Paragraph(markup(line), body))
    if not story:
        story.append(Paragraph("No analysis text available.", body))

    def canvas_factory(*args, **kwargs):
        kwargs["pageCompression"] = 0
        return Canvas(*args, **kwargs)

    doc.build(story, onFirstPage=decorate, onLaterPages=decorate, canvasmaker=canvas_factory)
    return output.getvalue()
