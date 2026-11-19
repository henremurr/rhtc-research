"""Printable RHTC trade report."""
from decimal import Decimal, ROUND_HALF_UP
from io import BytesIO
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import landscape, letter
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import LongTable, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


def build_report(account, year, groups, summaries):
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
        heading = "     ".join([ticker, *(line for line in summaries[ticker] if line.endswith(" | OPEN"))])
        rows = [[heading, "", "", "", "", ""],
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


def build_tax_lot_report(account, year, lots, ticker="", weekly_income=False):
    """Create a printable Form 8949 style tax lot schedule."""
    output = BytesIO()
    width, height = landscape(letter)
    doc = SimpleDocTemplate(output, pagesize=(width, height), leftMargin=28,
                            rightMargin=28, topMargin=75, bottomMargin=38,
                            title=f"RHTC Form 8949 Tax Lot Report {year}")
    ink = colors.HexColor("#182229")
    gold = colors.HexColor("#C6A45C")
    body = ParagraphStyle("TaxLot", fontName="Helvetica", fontSize=7, leading=8)
    logo = Path(__file__).parent / "static" / "apple-touch-icon.png"

    def decorate(canvas, document):
        canvas.saveState()
        canvas.drawImage(str(logo), 34, height-55, width=34, height=34, mask="auto")
        canvas.setFillColor(ink)
        canvas.setFont("Helvetica-Bold", 17)
        title = "RHTC Weekly Income Report - Form 8949" if weekly_income else "RHTC Tax Lot Report - Form 8949 columns"
        canvas.drawString(78, height-37, title)
        canvas.setFont("Helvetica", 10)
        scope = f"Account {account}   |   Tax year {year}" + (f"   |   Ticker {ticker}" if ticker else "")
        canvas.drawString(78, height-52, scope)
        canvas.setStrokeColor(gold)
        canvas.line(34, height-64, width-34, height-64)
        canvas.setFont("Helvetica", 8)
        canvas.drawRightString(width-34, 20, f"Rocking Horse Trading Co.   |   {document.page}")
        canvas.restoreState()

    headings = ["(a) Description", "(b) Acquired", "(c) Sold", "(d) Proceeds", "(e) Cost/basis", "(f) Code", "(g) Adjustment", "(h) Gain/loss"]
    def display_date(value):
        parts = value.split("-")
        return f"{parts[1]}/{parts[2]}/{parts[0]}" if len(parts) == 3 else value
    def money(value):
        return f"${Decimal(value):,.2f}" if value not in (None, "") else "--"

    story = []
    sections = (("short", "Part I - Short-term transactions (held 1 year or less)"),
                ("long", "Part II - Long-term transactions (held more than 1 year)"))
    totals = {term: {key: Decimal(0) for key in ("proceeds", "basis", "gain")} for term, _ in sections}
    for term, title in sections:
        selected = [lot for lot in lots if lot["term"] == term]
        if not selected:
            continue
        story.append(Paragraph(escape(title), ParagraphStyle("TaxLotSection", parent=body, fontName="Helvetica-Bold", fontSize=9, leading=12, textColor=ink)))
        data = [headings]
        for lot in selected:
            data.append([
                Paragraph(escape(lot["description"]), body), display_date(lot["acquired"]), display_date(lot["sold"]),
                money(lot["proceeds"]), money(lot["basis"]), lot["code"] or "",
                money(lot["adjustment"]) if lot["adjustment"] not in (None, "") else "", money(lot["gain"]),
            ])
            if lot["gain"] not in (None, ""):
                for key in totals[term]:
                    totals[term][key] += Decimal(lot[key])
        table = LongTable(data, colWidths=[142, 62, 62, 82, 86, 48, 86, 80],
                          repeatRows=1, hAlign="LEFT", splitInRow=1)
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), ink), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"), ("FONTSIZE", (0, 0), (-1, -1), 7),
            ("VALIGN", (0, 0), (-1, -1), "TOP"), ("ALIGN", (3, 1), (-1, -1), "RIGHT"),
            ("BACKGROUND", (0, 1), (-1, -1), colors.white),
            ("LINEBELOW", (0, 0), (-1, 0), 1, gold), ("LINEBELOW", (0, 1), (-1, -1), .3, colors.HexColor("#D5DADD")),
            ("LEFTPADDING", (0, 0), (-1, -1), 4), ("RIGHTPADDING", (0, 0), (-1, -1), 4),
            ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ]))
        story.extend([table, Spacer(1, 9)])

    totals_data = [["Holding period", "Proceeds", "Cost or basis", "Net gain/(loss)"]]
    for term, label in (("short", "Short-term"), ("long", "Long-term")):
        totals_data.append([label, *(money(totals[term][key]) for key in ("proceeds", "basis", "gain"))])
    totals_table = Table(totals_data, colWidths=[260, 120, 140, 148], hAlign="LEFT")
    totals_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), ink), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"), ("FONTNAME", (0, -2), (-1, -1), "Helvetica-Bold"),
        ("ALIGN", (1, 1), (-1, -1), "RIGHT"), ("LINEBELOW", (0, 0), (-1, 0), 1, gold),
        ("LINEABOVE", (0, -2), (-1, -2), .7, gold), ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("LEFTPADDING", (0, 0), (-1, -1), 6), ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.extend([Paragraph("Capital gain/(loss) totals", ParagraphStyle("TaxLotSummaryHeading", parent=body, fontName="Helvetica-Bold", fontSize=10, leading=13, textColor=ink)), totals_table])
    doc.build(story, onFirstPage=decorate, onLaterPages=decorate)
    return output.getvalue()
