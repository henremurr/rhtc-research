from __future__ import annotations

import html
import re
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    KeepTogether,
    ListFlowable,
    ListItem,
    PageTemplate,
    PageBreak,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)
from reportlab.platypus.tableofcontents import TableOfContents


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "USER_GUIDE.md"
OUTPUT = ROOT / "output" / "pdf" / "RHTC_User_Guide.pdf"
FONT_DIR = ROOT / "assets" / "fonts"
FONT_REGULAR = "Helvetica"
FONT_BOLD = "Helvetica-Bold"
if (FONT_DIR / "DejaVuSans.ttf").is_file() and (FONT_DIR / "DejaVuSans-Bold.ttf").is_file():
    pdfmetrics.registerFont(TTFont("RHTCSans", str(FONT_DIR / "DejaVuSans.ttf")))
    pdfmetrics.registerFont(TTFont("RHTCSans-Bold", str(FONT_DIR / "DejaVuSans-Bold.ttf")))
    pdfmetrics.registerFontFamily(
        "RHTCSans",
        normal="RHTCSans",
        bold="RHTCSans-Bold",
        italic="RHTCSans",
        boldItalic="RHTCSans-Bold",
    )
    FONT_REGULAR = "RHTCSans"
    FONT_BOLD = "RHTCSans-Bold"


def ascii_text(value: str) -> str:
    return (
        value.replace("\u2011", "-")
        .replace("\u2013", "-")
        .replace("\u2014", "-")
        .replace("\u2212", "-")
        .replace("\u00d7", "x")
        .replace("\u00f7", "/")
        .replace("\u00b7", "|")
        .replace("\u2018", "'")
        .replace("\u2019", "'")
        .replace("\u201c", '"')
        .replace("\u201d", '"')
    )


def inline_markup(value: str) -> str:
    value = ascii_text(value)
    links: list[str] = []

    def keep_link(match: re.Match[str]) -> str:
        label = html.escape(match.group(1))
        url = html.escape(match.group(2), quote=True)
        links.append(f'<link href="{url}" color="#8b6518">{label}</link>')
        return f"@@LINK{len(links) - 1}@@"

    value = re.sub(r"\[([^\]]+)\]\((https?://[^)\s]+)\)", keep_link, value)
    value = html.escape(value)
    value = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", value)
    value = re.sub(r"`([^`]+)`", f'<font name="{FONT_REGULAR}" size="8">\\1</font>', value)
    for index, link in enumerate(links):
        value = value.replace(f"@@LINK{index}@@", link)
    return value


class HeadingParagraph(Paragraph):
    def __init__(self, text: str, style: ParagraphStyle, level: int, slug: str):
        super().__init__(text, style)
        self.heading_level = level
        self.heading_slug = slug
        self.heading_text = re.sub(r"<[^>]+>", "", text)


class GuideDocTemplate(BaseDocTemplate):
    def afterFlowable(self, flowable):
        level = getattr(flowable, "heading_level", None)
        if level is None:
            return
        key = flowable.heading_slug
        self.canv.bookmarkPage(key)
        self.canv.addOutlineEntry(flowable.heading_text, key, level=level, closed=False)
        self.notify("TOCEntry", (level, flowable.heading_text, self.page, key))


def draw_page(canvas, doc):
    canvas.saveState()
    width, height = letter
    canvas.setStrokeColor(colors.HexColor("#d8c99f"))
    canvas.setLineWidth(0.5)
    canvas.line(doc.leftMargin, 0.55 * inch, width - doc.rightMargin, 0.55 * inch)
    canvas.setFont(FONT_REGULAR, 8)
    canvas.setFillColor(colors.HexColor("#68717c"))
    canvas.drawString(doc.leftMargin, 0.38 * inch, "RHTC THREE PEAKS RESEARCH PLATFORM | USER GUIDE")
    canvas.drawRightString(width - doc.rightMargin, 0.38 * inch, f"Page {doc.page}")
    canvas.restoreState()


def make_styles():
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle("GuideTitle", parent=styles["Title"], fontName=FONT_BOLD, fontSize=23, leading=28, alignment=TA_CENTER, textColor=colors.HexColor("#173047"), spaceAfter=14))
    styles.add(ParagraphStyle("GuideMeta", parent=styles["Normal"], fontName=FONT_REGULAR, fontSize=9, leading=13, alignment=TA_CENTER, textColor=colors.HexColor("#6d7480"), spaceAfter=4))
    styles.add(ParagraphStyle("GuideH1", parent=styles["Heading1"], fontName=FONT_BOLD, fontSize=16, leading=20, textColor=colors.HexColor("#173047"), spaceBefore=13, spaceAfter=7, keepWithNext=True))
    styles.add(ParagraphStyle("GuideH2", parent=styles["Heading2"], fontName=FONT_BOLD, fontSize=12, leading=15, textColor=colors.HexColor("#80621f"), spaceBefore=9, spaceAfter=4, keepWithNext=True))
    styles.add(ParagraphStyle("GuideH3", parent=styles["Heading3"], fontName=FONT_BOLD, fontSize=10, leading=13, textColor=colors.HexColor("#34495e"), spaceBefore=7, spaceAfter=3, keepWithNext=True))
    styles.add(ParagraphStyle("GuideBody", parent=styles["BodyText"], fontName=FONT_REGULAR, fontSize=9, leading=13, textColor=colors.HexColor("#222a32"), spaceAfter=6, splitLongWords=1))
    styles.add(ParagraphStyle("GuideBullet", parent=styles["BodyText"], fontName=FONT_REGULAR, fontSize=8.7, leading=12, textColor=colors.HexColor("#222a32"), spaceAfter=2, splitLongWords=1))
    styles.add(ParagraphStyle("GuideCell", parent=styles["BodyText"], fontName=FONT_REGULAR, fontSize=7.7, leading=10, textColor=colors.HexColor("#222a32"), spaceAfter=1, splitLongWords=1))
    styles.add(ParagraphStyle("GuideCellHead", parent=styles["GuideCell"], fontName=FONT_BOLD, textColor=colors.HexColor("#173047")))
    styles.add(ParagraphStyle("GuideTOC", parent=styles["Normal"], fontName=FONT_REGULAR, fontSize=9, leading=13, leftIndent=12, firstLineIndent=-12, spaceAfter=3))
    return styles


def slugify(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-") or "section"


def markdown_story(markdown: str, styles):
    story = []
    paragraph_lines: list[str] = []
    bullet_items: list[str] = []
    toc = TableOfContents()
    toc.levelStyles = [
        ParagraphStyle("TOCLevel0", parent=styles["GuideTOC"], fontName=FONT_BOLD, leftIndent=0),
        ParagraphStyle("TOCLevel1", parent=styles["GuideTOC"], leftIndent=16),
        ParagraphStyle("TOCLevel2", parent=styles["GuideTOC"], leftIndent=30, fontSize=8),
    ]
    in_toc = False
    title_seen = False
    headings: dict[int, int] = {1: 0, 2: 0, 3: 0}

    def flush_paragraph():
        nonlocal paragraph_lines
        if paragraph_lines:
            story.append(Paragraph(inline_markup(" ".join(paragraph_lines)), styles["GuideBody"]))
            paragraph_lines = []

    def flush_bullets():
        nonlocal bullet_items
        if bullet_items:
            items = [ListItem(Paragraph(inline_markup(item), styles["GuideBullet"]), leftIndent=10) for item in bullet_items]
            story.append(ListFlowable(items, bulletType="bullet", start="circle", leftIndent=18, bulletFontName=FONT_REGULAR, bulletFontSize=6, spaceAfter=6))
            bullet_items = []

    def flush_text():
        flush_paragraph()
        flush_bullets()

    lines = markdown.splitlines()
    index = 0
    while index < len(lines):
        raw = lines[index]
        line = raw.strip()
        if not line:
            flush_text()
            index += 1
            continue
        heading = re.match(r"^(#{1,3})\s+(.+)$", line)
        if heading:
            flush_text()
            depth = len(heading.group(1))
            text = heading.group(2).strip()
            if depth == 1 and not title_seen:
                story.append(Paragraph(inline_markup(text), styles["GuideTitle"]))
                title_seen = True
                index += 1
                continue
            if text.lower() == "table of contents":
                story.append(Paragraph("Table of contents", styles["GuideH1"]))
                story.append(Spacer(1, 4))
                story.append(toc)
                in_toc = True
                index += 1
                continue
            if in_toc:
                in_toc = False
            headings[depth] += 1
            for deeper in range(depth + 1, 4):
                headings[deeper] = 0
            slug = slugify(text)
            if depth == 2:
                level = 0
                style = styles["GuideH1"]
            else:
                level = depth - 2
                style = styles["GuideH2"] if depth == 2 else styles["GuideH3"]
            story.append(HeadingParagraph(inline_markup(text), style, level, f"{slug}-{headings[depth]}"))
            index += 1
            continue
        if in_toc and re.match(r"^\d+\.\s+", line):
            index += 1
            continue
        if line.startswith("|") and index + 1 < len(lines) and re.match(r"^\s*\|?\s*:?-{3,}", lines[index + 1]):
            flush_text()
            table_rows = [[cell.strip() for cell in line.strip("|").split("|")]]
            index += 2
            while index < len(lines) and lines[index].strip().startswith("|"):
                table_rows.append([cell.strip() for cell in lines[index].strip().strip("|").split("|")])
                index += 1
            header = table_rows[0]
            body = table_rows[1:]
            formatted = [[Paragraph(inline_markup(cell), styles["GuideCellHead"]) for cell in header]]
            formatted.extend([[Paragraph(inline_markup(cell), styles["GuideCell"]) for cell in row] for row in body])
            widths = [1.9 * inch, 4.85 * inch] if len(header) == 2 else [6.75 * inch / len(header)] * len(header)
            table = Table(formatted, colWidths=widths, repeatRows=1, hAlign="LEFT")
            table.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e9edf1")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#173047")),
                ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#c7ced5")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f7f8fa")]),
            ]))
            story.extend([KeepTogether([table]), Spacer(1, 7)])
            continue
        bullet = re.match(r"^[-*]\s+(.+)$", line)
        ordered = re.match(r"^\d+\.\s+(.+)$", line)
        if bullet or ordered:
            flush_paragraph()
            bullet_items.append((bullet or ordered).group(1))
            index += 1
            continue
        paragraph_lines.append(line)
        index += 1

    flush_text()
    return story


def build_pdf(source: Path = SOURCE, output: Path = OUTPUT) -> Path:
    output.parent.mkdir(parents=True, exist_ok=True)
    styles = make_styles()
    doc = GuideDocTemplate(
        str(output),
        pagesize=letter,
        leftMargin=0.72 * inch,
        rightMargin=0.72 * inch,
        topMargin=0.72 * inch,
        bottomMargin=0.78 * inch,
        title="RHTC Three Peaks Research Platform User Guide",
        author="Rocking Horse Trading Co.",
    )
    frame = Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height, id="normal")
    doc.addPageTemplates([PageTemplate(id="guide", frames=[frame], onPage=draw_page)])
    content = source.read_text(encoding="utf-8")
    doc.multiBuild(markdown_story(content, styles))
    return output


if __name__ == "__main__":
    print(build_pdf())
