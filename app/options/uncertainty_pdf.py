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
    in_dimensions = False
    seen_dimensions = set()
    for raw in analysis.splitlines():
        line = raw.strip()
        if not line:
            continue
        match = re.match(r"^(#{1,6})\s+(.+)", line)
        if match and len(match[1]) <= 2:
            in_dimensions = bool(re.search(r"seven dimensions of structural uncertainty", match[2], re.I))
            seen_dimensions.clear()
        if in_dimensions:
            candidate = re.sub(r"^(?:#{1,6}\s+|[-*]\s+|\d+(?:\.\d+)*[.)]?\s+)", "", line).replace("**", "")
            dimension = re.match(r"^(Technological|Economic|Monetary|Geopolitical|Energy|Societal|Financial)\s+uncertainty(?:\s*(?:[:—–-]|$))", candidate, re.I)
            if dimension and dimension[1].lower() not in seen_dimensions:
                seen_dimensions.add(dimension[1].lower())
                yield "dimension", dimension[0].rstrip(" :—–-")
                tail = candidate[dimension.end():].strip()
                if tail:
                    yield "body", tail
                continue
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
            level = getattr(flowable, "outline_level", 0)
            self.canv.addOutlineEntry(title, key, level=level, closed=False)
            self.notify("TOCEntry", (level, title, self.page, key))


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
    dimension_style = ParagraphStyle("Dimension", parent=subheading, fontSize=15, leading=20, backColor=colors.HexColor("#FAF5E8"), borderPadding=6, spaceBefore=18, spaceAfter=10)
    minor = ParagraphStyle("Minor", parent=body, fontName="Helvetica-Bold", fontSize=11.5, leading=16, spaceBefore=8, spaceAfter=4, keepWithNext=True)
    bullet = ParagraphStyle("List", parent=body, leftIndent=16, firstLineIndent=-12)
    logo = Path(__file__).parent / "static" / "apple-touch-icon.png"

    def cover(canvas, document):
        canvas.saveState()
        canvas.setStrokeColor(gold)
        canvas.setLineWidth(1.2)
        canvas.rect(36, 36, width-72, height-72, stroke=1, fill=0)
        canvas.setFillColor(ink)
        canvas.setFont("Helvetica-Bold", 11)
        canvas.drawCentredString(width/2, height-86, "ROCKING HORSE TRADING CO.")
        canvas.drawImage(str(logo), (width-126)/2, height-252, width=126, height=126, mask="auto")
        canvas.setFillColor(colors.HexColor("#78591F"))
        canvas.setFont("Helvetica-Bold", 12)
        canvas.drawCentredString(width/2, height-290, "THREE PEAKS RESEARCH")
        canvas.line(100, height-309, width-100, height-309)
        canvas.setFillColor(ink)
        canvas.setFont("Helvetica-Bold", 29)
        canvas.drawCentredString(width/2, height-363, "Investing in the Age of")
        canvas.drawCentredString(width/2, height-399, "Structural Uncertainty")
        canvas.setFont("Helvetica", 15)
        canvas.drawCentredString(width/2, height-445, "Expanded Strategic Investment Report")
        canvas.setFont("Helvetica", 11)
        canvas.drawCentredString(width/2, height-478, "Portfolio Strategy | Risk | Opportunity | The Long Game")
        canvas.setFont("Helvetica-Bold", 10)
        canvas.drawCentredString(width/2, 202, "REPORT GENERATION DATE")
        canvas.setFont("Helvetica", 12)
        canvas.drawCentredString(width/2, 182, str(as_of))
        canvas.setStrokeColor(gold)
        canvas.line(100, 126, width-100, 126)
        canvas.setFont("Helvetica", 9)
        canvas.drawCentredString(width/2, 103, "RHTC | Investment research and strategic analysis")
        canvas.drawCentredString(width/2, 88, "Informational research; not an instruction to execute trades.")
        canvas.restoreState()

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
    story = [Spacer(1, 1), PageBreak()]
    if any(kind == "section" for kind, _ in blocks):
        story.append(Paragraph("Table of Contents", heading))
        toc = TableOfContents()
        toc.levelStyles = [ParagraphStyle("ContentsEntry", parent=body, fontSize=10.5,
                                          leading=15, spaceAfter=4, leftIndent=12,
                                          firstLineIndent=-12), ParagraphStyle("ContentsDimension", parent=body, fontSize=10, leading=14, leftIndent=28, spaceAfter=3)]
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
        elif kind == "dimension":
            names = ("technological", "economic", "monetary", "geopolitical", "energy", "societal", "financial")
            number = names.index(line.split()[0].lower()) + 1
            para = Paragraph(markup(f"{section}.{number} {line.title()}"), dimension_style)
            para.outline_key = f"dimension-{section}-{number}"
            para.outline_level = 1
            story.append(para)
        elif kind == "subsection":
            subsection += 1
            prefix = f"{section}.{subsection} " if section and not (section == 2 and any(k == "dimension" for k, _ in blocks)) else ""
            story.append(Paragraph(markup(prefix + line), subheading))
        elif kind == "minor":
            story.append(Paragraph(markup(line), minor))
        elif kind == "rule":
            story.append(HRFlowable(width="100%", thickness=0.6, color=gold, spaceBefore=7, spaceAfter=7))
        else:
            story.append(Paragraph(markup(line), bullet if kind == "list" else body))
    if not blocks:
        story.append(Paragraph("No analysis text available.", body))

    def canvas_factory(*args, **kwargs):
        kwargs["pageCompression"] = 0
        return Canvas(*args, **kwargs)

    doc.multiBuild(story, onFirstPage=cover, onLaterPages=decorate, canvasmaker=canvas_factory)
    return output.getvalue()
