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


DIMENSION_NAMES = ("Technological", "Economic", "Monetary", "Geopolitical", "Energy", "Societal", "Financial")
DIMENSION_ALIASES = (
    r"technolog(?:ical|y)|innovation",
    r"economic|macroeconomic|economy|macro",
    r"monetary|interest rates?|monetary policy",
    r"geopolitical|geopolitics|geopolitical and trade",
    r"energy|energy and infrastructure|power and energy",
    r"societal|social|society|social and labor",
    r"financial|financial markets?|capital markets?|financial and market",
)


DIMENSION_LEADS = (
    r"technolog(?:ical|y)|innovation",
    r"macroeconomic|economic|economy|macro",
    r"monetary|interest rates?",
    r"geopolitical|geopolitics",
    r"energy|power",
    r"societal|social|society",
    r"financial|capital markets?",
)
DIMENSION_COMPOUND = re.compile(r"""^(?P<lead>technolog(?:ical|y)|innovation|macroeconomic|economic|economy|macro|monetary|interest rates?|geopolitical|geopolitics|energy|power|societal|social|society|financial|capital markets?)\b(?P<qualifier>[^:\n—–]{0,100}?)\b(?:uncertaint(?:y|ies)|risks?|dimensions?)\s*(?=$|[:—–-]|\()""", re.I)


def dimension_heading(line):
    """Identify compound headings and preserve their original qualifiers."""
    candidate = line.replace("**", "").replace("__", "").strip()
    candidate = re.sub(r"^(?:(?:#{1,6}|[-*•])\s+|(?:dimension\s+)?\(?\d+(?:\.\d+)*[.)\]:-]?\s+)+", "", candidate, flags=re.I)
    match = DIMENSION_COMPOUND.match(candidate)
    if match:
        lead = match["lead"]
        for index, alias in enumerate(DIMENSION_LEADS):
            if re.fullmatch(alias, lead, re.I):
                tail = candidate[match.end():].strip()
                tail = re.sub(r"^[:—–-]\s*", "", tail)
                label = candidate[:match.end()].strip()
                canonical = DIMENSION_NAMES[index] + " uncertainty"
                if label.casefold() != canonical.casefold():
                    tail = label + (" — " + tail if tail else "")
                return index, tail
    # Legacy short labels without an explicit uncertainty/risk suffix.
    for index, alias in enumerate(DIMENSION_ALIASES):
        match = re.match(rf"^({alias})(?:\s+(?:structural\s+)?(?:uncertainty|risk|dimension))?\s*(?=$|[:—–-]|\()", candidate, re.I)
        if match:
            tail = re.sub(r"^[:—–-]\s*", "", candidate[match.end():].strip())
            return index, tail
    return None


def plain_subheading(line, separated, following):
    """Conservative recognition of standalone legacy title lines."""
    if not separated or not following or len(line) > 140 or not 3 <= len(line.split()) <= 20:
        return False
    if not re.match(r"^[A-Z0-9]", line) or re.search(r"[.!?;]$|^(?:https?://|www\.|\|)", line):
        return False
    if re.match(r"^(?:This|These|Those|There|It|They|We|I|The report|The portfolio|For example)\b", line, re.I):
        return False
    if re.search(r"\b(?:is|are|was|were|has|have|will|should|must|can|could|would|may|might)\b", line, re.I):
        return False
    return len(following) > len(line) or bool(re.match(r"^(?:\*\*|[A-Z][^:]{2,100}:)", following))


def colon_heading(line):
    """Keep title qualifiers attached to their heading; preserve ambiguous prose inline."""
    label = re.match(r"^(\*\*[^*]{2,100}\*\*:?|[A-Z][^.!?;:]{2,85}:)\s+(.+)$", line)
    if not label:
        return None
    prefix, rest = label.groups()
    # Explicit bold spans already encode the author's intended boundary.
    if prefix.startswith("**") and ":" in prefix.rstrip(":").strip("*"):
        return prefix.replace("**", ""), rest
    prefix = prefix.replace("**", "").rstrip(":").strip()
    # A short topic qualifier followed by a sentence is part of the title.
    boundary = re.match(r"^(.{2,140}?)[.!?]\s+([A-Z0-9].+)$", rest)
    if boundary:
        qualifier, body = boundary.groups()
        if (len(qualifier.split()) <= 20 and
                (re.match(r"^(?:what|why|how|when|where|which|whether)\b", qualifier, re.I)
                 or not re.search(r"\b(?:is|are|was|were|has|have|will|should|must|can|could|would|may|might)\b", qualifier, re.I))
                and (qualifier[0].islower() or re.match(r"^(?:what|why|how|when|where|which|whether)\b", qualifier, re.I))):
            return prefix + ": " + qualifier, body
    if len(rest) <= 140 and len(rest.split()) <= 20 and not re.search(r"[.!?]$", rest):
        if not re.search(r"\b(?:is|are|was|were|has|have|will|should|must|can|could|would|may|might)\b", rest, re.I):
            return prefix + ": " + rest, ""
    # Explicit bold label is reliable; an unmarked colon is not a heading boundary.
    if label[1].startswith("**"):
        return prefix + ":", rest
    return None


def list_levels(analysis):
    """Preserve explicit list depth and infer numbered children after colon-led bullets."""
    stack = []
    levels = {}
    for pos, raw in enumerate(analysis.splitlines()):
        if not raw.strip():
            continue
        match = re.match(r"^([ \t]*)([-*+]|\d+[.)])\s+(.+)$", raw)
        if not match:
            stack.clear()
            continue
        indent = len(match[1].expandtabs(4))
        marker, content = match.group(2, 3)
        ordered = marker[0].isdigit()
        while stack and indent < stack[-1]["indent"]:
            stack.pop()
        if not stack:
            stack.append({"indent": indent, "ordered": ordered, "level": 0, "parent": False, "inferred": False})
        elif indent > stack[-1]["indent"]:
            stack.append({"indent": indent, "ordered": ordered, "level": stack[-1]["level"] + 1, "parent": False, "inferred": False})
        elif stack[-1]["inferred"] and not ordered:
            stack.pop()
        elif ordered and not stack[-1]["ordered"] and stack[-1]["parent"]:
            stack.append({"indent": indent, "ordered": True, "level": stack[-1]["level"] + 1, "parent": False, "inferred": True})
        current = stack[-1]
        current["ordered"] = ordered
        current["parent"] = not ordered and content.rstrip().endswith(":")
        levels[pos] = min(current["level"], 6)
    return levels


def narrative_blocks(analysis):
    """Recognize explicit headings and short prose labels without dropping content."""
    in_dimensions = False
    seen_dimensions = set()
    lines = analysis.splitlines()
    levels = list_levels(analysis)
    for pos, raw in enumerate(lines):
        line = raw.strip()
        if not line:
            continue
        match = re.match(r"^(#{1,6})\s+(.+)", line)
        if match and len(match[1]) <= 2:
            if in_dimensions:
                missing = [name for i, name in enumerate(DIMENSION_NAMES) if i not in seen_dimensions]
                if missing:
                    yield "body", "Navigation note: no distinct heading could be located in this saved section for " + ", ".join(missing) + ". The original narrative is retained below or above as supplied; regenerate if coverage is incomplete."
            in_dimensions = bool(re.search(r"seven dimensions of structural uncertainty", match[2], re.I))
            seen_dimensions.clear()
        if in_dimensions:
            dimension = dimension_heading(line)
            if dimension and dimension[0] not in seen_dimensions:
                index, tail = dimension
                seen_dimensions.add(index)
                yield "dimension", DIMENSION_NAMES[index] + " uncertainty"
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
        if pos in levels:
            yield f"list:{levels[pos]}", line
            continue
        separated = pos == 0 or not lines[pos-1].strip()
        following = next((s.strip() for s in lines[pos+1:pos+4] if s.strip()), "")
        if not in_dimensions and plain_subheading(line, separated, following):
            yield "subsection", line
            continue
        label = colon_heading(line)
        if label:
            yield ("minor" if in_dimensions else "subsection"), label[0]
            if label[1]:
                yield "body", label[1]
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
            self.notify("TOCEntry", (level, escape(title), self.page, key))


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
    subheading = ParagraphStyle("Subsection", parent=body, fontName="Helvetica-Bold", fontSize=15, leading=20, spaceBefore=18, spaceAfter=10, keepWithNext=True, textColor=colors.black, backColor=None, borderPadding=0)
    dimension_style = ParagraphStyle("Dimension", parent=subheading, fontSize=15, leading=20, backColor=None, borderPadding=0, spaceBefore=18, spaceAfter=10)
    minor = ParagraphStyle("Minor", parent=body, fontName="Helvetica-Bold", fontSize=11.5, leading=16, spaceBefore=8, spaceAfter=4, keepWithNext=True, textColor=colors.black)
    bullets = [ParagraphStyle(f"List{depth}", parent=body, leftIndent=18 + 22*depth,
                              firstLineIndent=-14, spaceAfter=7) for depth in range(7)]
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
        toc.dotsMinLevel = 0
        toc.levelStyles = [ParagraphStyle("ContentsEntry", parent=body, fontSize=10.5,
                                          leading=15, spaceAfter=4, leftIndent=12,
                                          firstLineIndent=-12), ParagraphStyle("ContentsSubsection", parent=body, fontSize=10, leading=14, leftIndent=28, spaceAfter=3), ParagraphStyle("ContentsMinor", parent=body, fontSize=9, leading=12, leftIndent=43, spaceAfter=2)]
        story.extend([toc, PageBreak()])
    section = subsection = detail = 0
    in_dimensions = False
    outline_serial = 0

    def add_heading(label, style, level):
        nonlocal outline_serial
        outline_serial += 1
        para = Paragraph(markup(label), style)
        para.outline_key = f"heading-{outline_serial}"
        para.outline_level = level
        story.append(para)

    for kind, line in blocks:
        if kind == "section":
            section += 1
            subsection = detail = 0
            in_dimensions = "seven dimensions of structural uncertainty" in line.lower()
            add_heading(f"{section}. {line}", heading, 0)
        elif kind == "dimension":
            subsection = DIMENSION_NAMES.index(line.split()[0].capitalize()) + 1
            detail = 0
            add_heading(f"{section}.{subsection} {line.title()}", dimension_style, 1)
        elif kind == "subsection" and not in_dimensions:
            subsection += 1
            detail = 0
            if section:
                add_heading(f"{section}.{subsection} {line}", subheading, 1)
            else:
                story.append(Paragraph(markup(line), subheading))
        elif kind in ("minor", "subsection"):
            detail += 1
            if section and subsection:
                add_heading(f"{section}.{subsection}.{detail} {line}", minor, 2)
            elif section and not in_dimensions:
                subsection += 1
                detail = 0
                add_heading(f"{section}.{subsection} {line}", subheading, 1)
            else:
                story.append(Paragraph(markup(line), minor))
        elif kind == "rule":
            story.append(HRFlowable(width="100%", thickness=0.6, color=gold, spaceBefore=7, spaceAfter=7))
        else:
            story.append(Paragraph(markup(line), bullets[int(kind.split(":")[1])] if kind.startswith("list:") else body))
    if not blocks:
        story.append(Paragraph("No analysis text available.", body))

    def canvas_factory(*args, **kwargs):
        kwargs["pageCompression"] = 0
        return Canvas(*args, **kwargs)

    doc.multiBuild(story, maxPasses=30, onFirstPage=cover, onLaterPages=decorate, canvasmaker=canvas_factory)
    return output.getvalue()
