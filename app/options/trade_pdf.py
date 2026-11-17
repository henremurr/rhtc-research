"""Printable RHTC trade report."""
from decimal import Decimal, ROUND_HALF_UP
from io import BytesIO
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import landscape, letter
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import LongTable, Paragraph, SimpleDocTemplate, Spacer, TableStyle


def build_report(account, year, groups):
    output = BytesIO()
    width, height = landscape(letter)
    doc = SimpleDocTemplate(output, pagesize=(width, height), leftMargin=32,
                            rightMargin=32, topMargin=75, bottomMargin=38,
                            title=f"RHTC Trade Report {year}")
    ink = colors.HexColor("#182229")
    gold = colors.HexColor("#C6A45C")
    body = ParagraphStyle("Trade", fontName="Helvetica", fontSize=8, leading=10)
    logo = Path(__file__).parent / "static" / "apple-touch-icon.png"

    def decorate(canvas, document):
        canvas.saveState()
        canvas.drawImage(str(logo), 38, height-55, width=34, height=34, mask="auto")
        canvas.setFillColor(ink)
        canvas.setFont("Helvetica-Bold", 17)
        canvas.drawString(82, height-37, "RHTC Trade Report")
        canvas.setFont("Helvetica", 10)
        canvas.drawString(82, height-52, f"Account {account}   |   {year}")
        canvas.setStrokeColor(gold)
        canvas.line(38, height-64, width-38, height-64)
        canvas.setFont("Helvetica", 8)
        canvas.drawRightString(width-38, 20, f"Rocking Horse Trading Co.   |   {document.page}")
        canvas.restoreState()

    def cents(value):
        return Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    story = []
    for ticker, trades in groups.items():
        rows = [[ticker, "", "", "", "", ""],
                ["Date", "Action", "Security", "Quantity", "Price ($)", "Amount ($)"]]
        amounts = []
        for day, action, symbol, quantity, price, amount in trades:
            if amount not in (None, ""):
                amounts.append(cents(amount))
            money = [f"{cents(v):,.2f}" if v not in (None, "") else "—" for v in (price, amount)]
            rows.append([day, Paragraph(escape(action), body), Paragraph(escape(symbol or "—"), body),
                         quantity if quantity not in (None, "") else "—", *money])
        rows.append([f"{ticker} net amount total ($)", "", "", "", "",
                     f"{sum(amounts):,.2f}" if amounts else "—"])
        table = LongTable(rows, colWidths=[69, 295, 108, 55, 83, 106], repeatRows=2,
                          hAlign="LEFT", splitInRow=1)
        table.setStyle(TableStyle([
            ("SPAN", (0, 0), (-1, 0)), ("BACKGROUND", (0, 0), (-1, 0), ink),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("BACKGROUND", (0, 1), (-1, 1), colors.HexColor("#E6E9EB")),
            ("FONTNAME", (0, 0), (-1, 1), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 8), ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("ALIGN", (3, 1), (-1, -1), "RIGHT"), ("SPAN", (0, -1), (4, -1)),
            ("NOSPLIT", (0, -2), (-1, -1)), ("LINEABOVE", (0, -1), (-1, -1), 1, gold),
            ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold")
        ]))
        story.extend([table, Spacer(1, 12)])
    doc.build(story, onFirstPage=decorate, onLaterPages=decorate)
    return output.getvalue()
