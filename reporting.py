from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    Image,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
)


def create_pdf(
    title: str,
    analyses: list[dict[str, Any]],
    output_dir: Path,
) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    filename = f"RHTC_Research_Report_{date.today().isoformat()}.pdf"
    output_path = output_dir / filename

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "RHTCTitle",
        parent=styles["Title"],
        alignment=TA_CENTER,
        fontSize=22,
        leading=26,
        spaceAfter=10,
    )
    subtitle_style = ParagraphStyle(
        "RHTCSubtitle",
        parent=styles["Normal"],
        alignment=TA_CENTER,
        fontSize=11,
        textColor=colors.HexColor("#6A5A38"),
        spaceAfter=20,
    )
    heading = ParagraphStyle(
        "RHTCHeading",
        parent=styles["Heading1"],
        fontSize=15,
        leading=18,
        spaceBefore=12,
        spaceAfter=7,
    )
    body = ParagraphStyle(
        "RHTCBody",
        parent=styles["BodyText"],
        fontSize=10.5,
        leading=15,
        spaceAfter=7,
    )

    doc = SimpleDocTemplate(
        str(output_path),
        pagesize=letter,
        rightMargin=0.65 * inch,
        leftMargin=0.65 * inch,
        topMargin=0.65 * inch,
        bottomMargin=0.65 * inch,
    )

    story = []
    logo = Path("assets/three_peaks_logo.jpeg")
    if logo.exists():
        story.append(Image(str(logo), width=2.25 * inch, height=2.25 * inch))
        story.append(Spacer(1, 0.15 * inch))

    story.append(Paragraph(title, title_style))
    story.append(Paragraph(date.today().strftime("%B %d, %Y"), subtitle_style))
    story.append(Paragraph(
        "AI Infrastructure • Energy, Fuels & Minerals / Infrastructure • "
        "Defense, Space & Infrastructure",
        subtitle_style,
    ))
    story.append(PageBreak())

    pillar_order = ["AI/I", "EFM/I", "DS/I", "Cross-Peak", "Other"]
    for pillar in pillar_order:
        items = [item for item in analyses if item.get("pillar") == pillar]
        if not items:
            continue
        story.append(Paragraph(pillar, heading))
        for item in items:
            headline = item.get("headline") or item.get("id", "Article")
            story.append(Paragraph(headline, styles["Heading2"]))
            story.append(Paragraph(
                f"<b>Assessment:</b> {item.get('assessment', 'neutral').title()} "
                f"• <b>Materiality:</b> Tier {item.get('materiality_tier', 3)}",
                body,
            ))
            story.append(Paragraph(item.get("summary", ""), body))

            for label, key in [
                ("Key facts", "key_facts"),
                ("Strategic significance", "strategic_significance"),
                ("Risks", "risks"),
            ]:
                values = item.get(key) or []
                if values:
                    story.append(Paragraph(f"<b>{label}</b>", body))
                    for value in values:
                        story.append(Paragraph(f"• {value}", body))
            story.append(Spacer(1, 8))

    def draw_page(canvas, document):
        canvas.saveState()
        width, height = letter
        canvas.setStrokeColor(colors.HexColor("#B99A52"))
        canvas.rect(24, 24, width - 48, height - 48)
        canvas.setFont("Helvetica", 8)
        canvas.drawRightString(width - 30, 17, str(document.page))
        canvas.restoreState()

    doc.build(story, onFirstPage=draw_page, onLaterPages=draw_page)
    return output_path
