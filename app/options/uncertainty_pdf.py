"""Render a stored investment strategy report without calling the analysis provider."""
import re
import unicodedata
from io import BytesIO
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, HRFlowable, PageBreak
from reportlab.pdfgen.canvas import Canvas
from reportlab.platypus.tableofcontents import TableOfContents


def normalize_pdf_text(value):
    """Map typography outside WinAnsi to printable equivalents for Helvetica."""
    substitutions = {
        0x2010: "-", 0x2011: "-", 0x2012: "-", 0x2212: "-",
        0x00AD: None, 0x200B: None, 0x2060: None, 0xFEFF: None,
        0x202F: " ", 0x2009: " ", 0x2007: " ", 0x00A0: " ",
        0x2192: "->", 0x2190: "<-", 0x2264: "<=", 0x2265: ">=",
        0x2248: "~", 0x2260: "!=", 0x2044: "/", 0x25AA: "-",
    }
    value = unicodedata.normalize("NFKC", str(value)).translate(substitutions)
    result = []
    for ch in value:
        if ch in "\n\r\t":
            result.append(ch)
            continue
        if unicodedata.category(ch) in ("Cf", "Cc"):
            continue
        try:
            ch.encode("cp1252")
            result.append(ch)
        except UnicodeEncodeError:
            # Keep otherwise unsupported characters identifiable, rather than
            # silently losing them or rendering an opaque missing-glyph box.
            result.append("[U+%04X]" % ord(ch))
    return "".join(result)


def narrative_blocks(analysis):
    """Recognize explicit headings and short prose labels without dropping content."""
    for raw in analysis.splitlines():
        line = raw.strip()
        if not line:
            continue
        match = re.match(r"^(#{1,6})\s+(.+)", line)
        if match:
            yield ("section" if len(match[1]) <= 2 else "subsection" if len(match[1]) == 3 else "minor", match[2])
            continue
        if re.fullmatch(r"[-*_]{3,}", line):
            yield "rule", line
            continue
        if re.fullmatch(r"\*\*[^*]{1,120}\*\*:?",""+line):
            yield "subsection", line.strip("*").rstrip(":").rstrip("*")
            continue
        if re.match(r"^(?:[-*]|\d+\.)\s+", line):
            yield "list", line
            continue
        label = re.match(r"^(\*\*[^*]{2,100}\*\*:?|[A-Z][^.!?;:]{2,85}:)\s+(.+)$", line)
        if label:
            yield "minor", label[1]
            yield "body", label[2]
        else:
            yield "body", line


class NarrativeDocument(SimpleDocTemplate):
    def afterFlowable(self, flowable):
        if isinstance(flowable, Paragraph) and getattr(flowable, "outline_key", None):
            key = flowable.outline_key
            title = flowable.getPlainText()
            self.canv.bookmarkPage(key)
            self.canv.addOutlineEntry(title, key, level=0, closed=False)
            self.notify("TOCEntry", (0, title, self.page, key))


def build_uncertainty_pdf(analysis, as_of):
    analysis = normalize_pdf_text(analysis)
    as_of = normalize_pdf_text(as_of)
    output = BytesIO()
    title = "Age of Structural Uncertainty"
    ink = colors.HexColor("#182229")
    gold = colors.HexColor("#C6A45C")
    width, height = letter
    doc = NarrativeDocument(output, pagesize=letter, leftMargin=50, rightMargin=50,
                            topMargin=82, bottomMargin=42, title=title, author="Rocking Horse Trading Co.")
    body = ParagraphStyle("Narrative", fontName="Helvetica", fontSize=11, leading=16,
                          spaceAfter=10, textColor=ink, splitLongWords=True)
    heading = ParagraphStyle("Section", parent=body, fontName="Helvetica-Bold",
                             fontSize=19, leading=24, spaceBefore=17, spaceAfter=10, keepWithNext=True,
                             backColor=colors.HexColor('#F4ECD7'), borderPadding=9)
    subheading = ParagraphStyle("Subsection", parent=body, fontName="Helvetica-Bold", fontSize=14, leading=19, spaceBefore=15, spaceAfter=7, keepWithNext=True, textColor=colors.HexColor("#78591F"))
    minor = ParagraphStyle("Minor", parent=body, fontName="Helvetica-Bold", fontSize=11.5, leading=16, spaceBefore=8, spaceAfter=4, keepWithNext=True)
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

    blocks = list(narrative_blocks(analysis))
    story = []
    if any(kind == "section" for kind, _ in blocks):
        story.append(Paragraph("Contents", heading))
        toc = TableOfContents()
        toc.levelStyles = [ParagraphStyle("ContentsEntry", parent=body, fontSize=10.5,
                                          leading=15, spaceAfter=4, leftIndent=12,
                                          firstLineIndent=-12)]
        story.extend([toc, PageBreak()])
    section = 0
    subsection = 0
    for kind, line in blocks:
        if kind == "section":
            section += 1
            subsection = 0
            para = Paragraph(markup(f"{section}. {line}"), heading)
            para.outline_key = f"section-{section}"
            story.append(para)
        elif kind == "subsection":
            subsection += 1
            prefix = f"{section}.{subsection} " if section else ""
            story.append(Paragraph(markup(prefix + line), subheading))
        elif kind == "minor":
            story.append(Paragraph(markup(line), minor))
        elif kind == "rule":
            story.append(HRFlowable(width="100%", thickness=0.6, color=gold, spaceBefore=7, spaceAfter=7))
        else:
            story.append(Paragraph(markup(line), bullet if kind == "list" else body))
    if not story:
        story.append(Paragraph("No analysis text available.", body))

    def canvas_factory(*args, **kwargs):
        kwargs["pageCompression"] = 0
        return Canvas(*args, **kwargs)

    doc.multiBuild(story, onFirstPage=decorate, onLaterPages=decorate, canvasmaker=canvas_factory)
    return output.getvalue()
