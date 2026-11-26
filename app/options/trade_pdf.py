from datetime import date, timedelta
"""Printable RHTC trade report."""
from decimal import Decimal, ROUND_HALF_UP
from io import BytesIO
from itertools import groupby
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import landscape, letter
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import LongTable, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


def draw_report_title(canvas, x, y, width, title):
    size = 17
    text_width = canvas.stringWidth(title, "Helvetica-Bold", size)
    if text_width > width:
        size *= width / text_width
    canvas.setFont("Helvetica-Bold", size)
    canvas.drawString(x, y, title)


def build_report(account, year, groups, summaries, title="", account_classification="Unknown / Unknown"):
    title = title.strip()[:300] or "Transaction report"
    output = BytesIO()
    width, height = landscape(letter)
    doc = SimpleDocTemplate(output, pagesize=(width, height), leftMargin=32,
                            rightMargin=32, topMargin=75, bottomMargin=38,
                            title=title)
    ink = colors.HexColor("#182229")
    gold = colors.HexColor("#C6A45C")
    body = ParagraphStyle("Trade", fontName="Helvetica", fontSize=8, leading=10)
    logo = Path(__file__).parent / "static" / "apple-touch-icon.png"

    def decorate(canvas, document):
        canvas.saveState()
        canvas.drawImage(str(logo), 38, height-55, width=34, height=34, mask="auto")
        canvas.setFillColor(ink)
        draw_report_title(canvas, 82, height-37, width-120, title)
        canvas.setFont("Helvetica", 10)
        canvas.drawString(82, height-52, f"Account {account}   |   {year}   |   {account_classification}")
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
        story.extend([table, Spacer(1, 4)])
    doc.build(story, onFirstPage=decorate, onLaterPages=decorate)
    return output.getvalue()


def weekly_income_rows(lots, year, include_details=False):
    """Summarize calendar-year sales in seven-day buckets beginning January 1."""
    start = date(year, 1, 1)
    year_end = date(year, 12, 31)
    buckets = {}
    for lot in lots:
        sold = date.fromisoformat(lot["sold"])
        week = min(52, (sold - start).days // 7 + 1)
        buckets.setdefault(week, []).append(lot)

    rows = []
    for week in range(1, max(buckets, default=0) + 1):
        entries = buckets.get(week, [])
        first = start + timedelta(weeks=week - 1)
        last = year_end if week == 52 else first + timedelta(days=6)
        row = {"week": week, "dates": f"{first:%m/%d} – {last:%m/%d}", "count": len(entries)}
        for key in ("proceeds", "basis", "gain"):
            values = [lot[key] for lot in entries]
            row[key] = None if any(value in (None, "") for value in values) else str(
                sum((Decimal(value) for value in values), Decimal("0.00")))
        if include_details:
            row["lots"] = sorted(entries, key=lambda lot: (
                lot["sold"], lot["ticker"], not lot["is_option"], lot["acquired"],
            ))
            row["ticker_groups"] = []
            for ticker, group in groupby(sorted(row["lots"], key=lambda lot: lot["ticker"]),
                                         key=lambda lot: lot["ticker"]):
                ticker_lots = list(group)
                subtotal = weekly_income_totals([
                    {"count": 1, **{key: lot[key] if lot[key] != "" else None
                                    for key in ("proceeds", "basis", "gain")}}
                    for lot in ticker_lots
                ])
                row["ticker_groups"].append({"ticker": ticker, "lots": ticker_lots, **subtotal})
        rows.append(row)
    return rows


def weekly_income_totals(weeks):
    totals = {"count": sum(week["count"] for week in weeks)}
    for key in ("proceeds", "basis", "gain"):
        values = [week[key] for week in weeks]
        totals[key] = None if None in values else str(
            sum((Decimal(value) for value in values), Decimal("0.00")))
    return totals


def build_tax_lot_report(account, year, lots, ticker="", weekly_income=False, weekly_detail=False, title="", account_classification="Unknown / Unknown"):
    """Create a printable Form 8949 style tax lot schedule."""
    if weekly_income:
        default_title = "Weekly Income Detail Report" if weekly_detail else "Weekly Income Summary Report"
    else:
        default_title = "Ticker tax lot report · Form 8949" if ticker else "Tax lot report · Form 8949"
    title = title.strip()[:300] or default_title
    if not weekly_income and account_classification == "Non-taxable / Cash":
        title = title.replace("Form 8949", "Internal performance only")
        if "Internal performance only" not in title:
            title += " - Internal performance only"
    output = BytesIO()
    width, height = landscape(letter)
    doc = SimpleDocTemplate(output, pagesize=(width, height), leftMargin=28,
                            rightMargin=28, topMargin=75, bottomMargin=38,
                            title=title)
    ink = colors.HexColor("#182229")
    gold = colors.HexColor("#C6A45C")
    body = ParagraphStyle("TaxLot", fontName="Helvetica", fontSize=7, leading=8)
    logo = Path(__file__).parent / "static" / "apple-touch-icon.png"

    def decorate(canvas, document):
        canvas.saveState()
        canvas.drawImage(str(logo), 34, height-55, width=34, height=34, mask="auto")
        canvas.setFillColor(ink)
        draw_report_title(canvas, 78, height-37, width-112, title)
        canvas.setFont("Helvetica", 10)
        scope = f"Account {account}   |   Tax year {year}" + (f"   |   Ticker {ticker}" if ticker else "")
        canvas.drawString(78, height-52, scope + "   |   " + account_classification)
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
    if weekly_income:
        data = [["Week", "Date range", "Closed lots", "Proceeds", "Cost basis", "Net gain/loss"]]
        weeks = weekly_income_rows(lots, int(year), include_details=weekly_detail)
        for row in weeks:
            data.append([row["week"], row["dates"], row["count"],
                         *(money(row[key]) for key in ("proceeds", "basis", "gain"))])
        totals = weekly_income_totals(weeks)
        data.append(["Total", "", totals["count"],
                     *(money(totals[key]) for key in ("proceeds", "basis", "gain"))])
        table = LongTable(data, repeatRows=1, colWidths=[60, 120, 90, 128, 128, 134])
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), ink),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("ALIGN", (2, 0), (-1, -1), "RIGHT"),
            ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
            ("LINEABOVE", (0, -1), (-1, -1), 1, gold),
            ("LINEBELOW", (0, 0), (-1, 0), 1, gold),
            ("LINEBELOW", (0, 1), (-1, -1), .3, colors.lightgrey),
        ]))
        story = [table]
        if weekly_detail:
            for week in weeks:
                if not week["lots"]:
                    continue
                heading = (f'Week {week["week"]} | {week["dates"]} | '
                           f'Net gain/loss {money(week["gain"])}')
                story.append(Spacer(1, 4))
                story.append(Paragraph(escape(heading), ParagraphStyle(
                    "WeeklyDetailHeading", parent=body, fontName="Helvetica-Bold",
                    fontSize=9, leading=11, spaceAfter=3)))
                detail = [headings]
                subtotals = []
                for group in week["ticker_groups"]:
                    for lot in group["lots"]:
                        detail.append([
                            Paragraph(escape(lot["description"]), body),
                            display_date(lot["acquired"]), display_date(lot["sold"]),
                            money(lot["proceeds"]), money(lot["basis"]), lot["code"] or "",
                            money(lot["adjustment"]) if lot["adjustment"] not in (None, "") else "",
                            money(lot["gain"]),
                        ])
                    subtotals.append(len(detail))
                    detail.append([f'{group["ticker"] or "Unknown ticker"} subtotal', "", "",
                                   money(group["proceeds"]), money(group["basis"]), "", "",
                                   money(group["gain"])])
                lots_table = LongTable(detail, repeatRows=1,
                                       colWidths=[142, 62, 62, 82, 86, 48, 86, 80])
                lots_table.setStyle(TableStyle([
                    ("BACKGROUND", (0, 0), (-1, 0), ink),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                    ("FONTSIZE", (0, 0), (-1, -1), 7),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("TOPPADDING", (0, 0), (-1, -1), 3),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                    ("ALIGN", (3, 0), (-1, -1), "RIGHT"),
                    ("LINEBELOW", (0, 1), (-1, -1), .3, colors.lightgrey),
                    *(("BACKGROUND", (0, index), (-1, index), colors.HexColor("#F0F2F3")) for index in subtotals),
                    *(("FONTNAME", (0, index), (-1, index), "Helvetica-Bold") for index in subtotals),
                    *(("LINEABOVE", (0, index), (-1, index), .75, gold) for index in subtotals),
                ]))
                story.append(lots_table)
        doc.build(story, onFirstPage=decorate, onLaterPages=decorate)
        return output.getvalue()

    sections = (("short", "Part I - Short-term transactions (held 1 year or less)"),
                ("long", "Part II - Long-term transactions (held more than 1 year)"))
    totals = {term: {key: Decimal(0) for key in ("proceeds", "basis", "gain")} for term, _ in sections}
    for term, section_title in sections:
        selected = [lot for lot in lots if lot["term"] == term]
        if not selected:
            continue
        story.append(Paragraph(escape(section_title), ParagraphStyle("TaxLotSection", parent=body, fontName="Helvetica-Bold", fontSize=9, leading=12, textColor=ink)))
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
            *(("LINEBELOW", (0, row), (-1, row), 1.4, ink)
              for row, (lot, next_lot) in enumerate(zip(selected, selected[1:]), start=1)
              if lot["sold"] != next_lot["sold"]),
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


def build_open_tax_lot_report(account, year, lots, title="", account_classification="Unknown / Unknown"):
    """Create a printable inventory of tax lots still open at year end."""
    title = title.strip()[:300] or "Open tax lot report"
    output = BytesIO()
    width, height = landscape(letter)
    doc = SimpleDocTemplate(output, pagesize=(width, height), leftMargin=34,
                            rightMargin=34, topMargin=75, bottomMargin=38,
                            title=title)
    ink = colors.HexColor("#182229")
    gold = colors.HexColor("#C6A45C")
    body = ParagraphStyle("OpenTaxLot", fontName="Helvetica", fontSize=8, leading=10)
    logo = Path(__file__).parent / "static" / "apple-touch-icon.png"

    def decorate(canvas, document):
        canvas.saveState()
        canvas.drawImage(str(logo), 38, height-55, width=34, height=34, mask="auto")
        canvas.setFillColor(ink)
        draw_report_title(canvas, 82, height-37, width-120, title)
        canvas.setFont("Helvetica", 10)
        canvas.drawString(82, height-52, f"Account {account}   |   As of {year}{' year-end' if str(year).isdigit() else ''}   |   {account_classification}")
        canvas.setStrokeColor(gold)
        canvas.line(38, height-64, width-38, height-64)
        canvas.setFont("Helvetica", 8)
        canvas.drawRightString(width-38, 20, f"Rocking Horse Trading Co.   |   {document.page}")
        canvas.restoreState()

    def money(value):
        if value in (None, ""):
            return "—"
        amount = Decimal(value)
        return f"-${abs(amount):,.2f}" if amount < 0 else f"${amount:,.2f}"

    data = [["Ticker / security", "Side", "Date acquired", "Holding period", "Open quantity", "Cost/Premium", "Per unit"]]
    subtotal_rows = []

    def group_key(lot):
        if lot.get("amount_type") in ("Cost", "Proceeds"):
            return ("stock", lot["ticker"])
        if lot.get("amount_type") == "Premium":
            security = lot["description"].split(" ", 2)[-1]
            return ("contract", lot["ticker"], security)
        return None

    def add_subtotal(group):
        if group[0].get("amount_type") in ("Cost", "Proceeds"):
            summary_lots = [lot for lot in group if lot.get("amount_type") == "Cost"]
            if not summary_lots:
                return
            label = f"Total Long · {group[0]['ticker']}"
            quantity = sum((Decimal(lot["quantity"]) for lot in summary_lots), Decimal(0))
            amount = sum((Decimal(lot["amount"]) for lot in summary_lots if lot.get("amount") not in (None, "")), Decimal(0))
            unit = amount / quantity if quantity else None
        else:
            summary_lots = [lot for lot in group if lot.get("amount_type") == "Premium" and lot.get("side") == "short"]
            if not summary_lots:
                return
            security = summary_lots[0]["description"].split(" ", 2)[-1]
            label = f"Total Short · {summary_lots[0]['ticker']} · {security}"
            quantity = sum((Decimal(lot["quantity"]) for lot in summary_lots), Decimal(0))
            amount = sum((Decimal(lot["amount"]) for lot in summary_lots if lot.get("amount") not in (None, "")), Decimal(0))
            unit = amount / (quantity * 100) if quantity else None
        data.append([Paragraph(escape(label), subtotal_style), "", "", "",
                     format(quantity.normalize(), ",f"), money(amount), money(unit) if unit is not None else "—"])
        subtotal_rows.append(len(data) - 1)

    subtotal_style = ParagraphStyle("OpenTaxLotSubtotal", parent=body, fontName="Helvetica-Bold")
    group_row_ranges = []
    active_key = None
    active_lots = []
    active_start = 1
    for lot in lots:
        key = group_key(lot)
        if key != active_key:
            if active_lots:
                before_subtotal = len(data)
                add_subtotal(active_lots)
                if len(data) > before_subtotal:
                    group_row_ranges.append((active_start, len(data) - 1))
            active_key, active_lots = key, []
            active_start = len(data)
        data.append([Paragraph(escape(lot["description"]), body), lot["side"].title(),
                     lot["acquired"], lot["term"].title(), lot["quantity"], money(lot["amount"]),
                     money(lot["unit_amount"])])
        if key is not None:
            active_lots.append(lot)
    if active_lots:
        before_subtotal = len(data)
        add_subtotal(active_lots)
        if len(data) > before_subtotal:
            group_row_ranges.append((active_start, len(data) - 1))
    table = LongTable(data, colWidths=[210, 60, 84, 80, 80, 100, 74], repeatRows=1,
                      hAlign="LEFT", splitInRow=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), ink), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"), ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("VALIGN", (0, 0), (-1, -1), "TOP"), ("ALIGN", (4, 1), (-1, -1), "RIGHT"),
        ("LINEBELOW", (0, 0), (-1, 0), 1, gold), ("LINEBELOW", (0, 1), (-1, -1), .3, colors.HexColor("#D5DADD")),
        ("LEFTPADDING", (0, 0), (-1, -1), 5), ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ] + [("LINEABOVE", (0, row), (-1, row), .75, gold) for row in subtotal_rows]
        + [("FONTNAME", (0, row), (-1, row), "Helvetica-Bold") for row in subtotal_rows]
        + [("BACKGROUND", (0, row), (-1, row), colors.HexColor("#F7F3E8")) for row in subtotal_rows]
        + [("NOSPLIT", (0, start), (-1, end)) for start, end in group_row_ranges]))
    doc.build([table], onFirstPage=decorate, onLaterPages=decorate)
    return output.getvalue()


def build_cash_activity_report(broker, account, groups, title="", account_classification="Unknown / Unknown"):
    output = BytesIO()
    width, height = landscape(letter)
    title = title.strip()[:300] or "Cash Activity Report"
    doc = SimpleDocTemplate(output, pagesize=(width, height), title=title,
                            leftMargin=34, rightMargin=34, topMargin=75, bottomMargin=38)
    body = ParagraphStyle("CashActivity", fontName="Helvetica", fontSize=8, leading=11)
    heading = ParagraphStyle("CashActivityHeading", fontName="Helvetica-Bold", fontSize=12,
                             leading=15)
    story = []
    ink = colors.HexColor("#182229")
    gold = colors.HexColor("#C6A45C")
    logo = Path(__file__).parent / "static" / "apple-touch-icon.png"

    def decorate(canvas, document):
        canvas.saveState()
        canvas.drawImage(str(logo), 38, height-55, width=34, height=34, mask="auto")
        canvas.setFillColor(ink)
        draw_report_title(canvas, 82, height-37, width-120, title)
        canvas.setFont("Helvetica", 10)
        canvas.drawString(82, height-52, f"{broker}   |   Account {account}   |   All dates   |   {account_classification}")
        canvas.setStrokeColor(gold)
        canvas.line(38, height-64, width-38, height-64)
        canvas.setFont("Helvetica", 8)
        canvas.drawRightString(width-38, 20, f"Rocking Horse Trading Co.   |   {document.page}")
        canvas.restoreState()

    def money(value):
        return "—" if value is None else f"${Decimal(value):,.2f}"

    if groups:
        summary_style = ParagraphStyle(
            "CashActivitySummaryHeading", fontName="Helvetica-Bold", fontSize=12,
            leading=15, textColor=ink, spaceAfter=5,
        )
        summary_rows = [["Activity type", "Transactions", "Net amount"]]
        valid_subtotals = []
        for group in groups:
            subtotal = group.get("subtotal")
            if subtotal is not None:
                valid_subtotals.append(Decimal(str(subtotal)))
            summary_rows.append([
                group["type"], str(len(group["rows"])), money(subtotal),
            ])
        total = sum(valid_subtotals, Decimal("0.00")) if len(valid_subtotals) == len(groups) else None
        summary_rows.append(["Net total", str(sum(len(group["rows"]) for group in groups)), money(total)])
        summary = Table(summary_rows, colWidths=[365, 100, 130], hAlign="LEFT", repeatRows=1)
        summary.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), ink),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
            ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#F0F2F3")),
            ("ALIGN", (1, 1), (-1, -1), "RIGHT"),
            ("LINEBELOW", (0, 0), (-1, 0), 1, gold),
            ("LINEABOVE", (0, -1), (-1, -1), 1, gold),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]))
        story.extend([Paragraph("Cash activity summary", summary_style), summary, Spacer(1, 10)])

    for group in groups:
        story.append(Paragraph(escape(group["type"]), heading))
        rows = [["Date", "Transaction", "Ticker", "Description", "Amount"]]
        for row in group["rows"]:
            rows.append([row["date"] or "—", Paragraph(escape(row["action"] or ""), body),
                         row["symbol"] or "—", Paragraph(escape(row["description"] or ""), body),
                         money(row["amount"])])
        rows.append(["Subtotal", "", "", "", money(group["subtotal"])])
        table = LongTable(rows, colWidths=[75, 175, 80, 283, 85], repeatRows=1, splitInRow=1)
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), ink),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("ALIGN", (-1, 0), (-1, -1), "RIGHT"),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LINEABOVE", (0, -1), (-1, -1), 1, gold),
            ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
        ]))
        story.extend([table, Spacer(1, 12)])
    doc.build(story, onFirstPage=decorate, onLaterPages=decorate)
    return output.getvalue()


def build_holdings_report(account, timestamp, headings, rows, summary, note):
    output = BytesIO()
    width, height = landscape(letter)
    title = f"Holdings Report for {account}"
    doc = SimpleDocTemplate(output, pagesize=(width, height), title=title,
                            leftMargin=34, rightMargin=34, topMargin=75, bottomMargin=38)
    ink = colors.HexColor("#182229")
    gold = colors.HexColor("#C6A45C")
    logo = Path(__file__).parent / "static" / "apple-touch-icon.png"
    body = ParagraphStyle("Holdings", fontName="Helvetica", fontSize=8, leading=11)
    header = ParagraphStyle("HoldingsHeader", parent=body, fontName="Helvetica-Bold",
                            textColor=colors.white)

    def decorate(canvas, document):
        canvas.saveState()
        canvas.drawImage(str(logo), 38, height-55, width=34, height=34, mask="auto")
        canvas.setFillColor(ink)
        draw_report_title(canvas, 82, height-37, width-120, title)
        canvas.setFont("Helvetica", 10)
        canvas.drawString(82, height-52, f"As of {timestamp}")
        canvas.setStrokeColor(gold)
        canvas.line(38, height-64, width-38, height-64)
        canvas.setFont("Helvetica", 8)
        canvas.drawRightString(width-38, 20, f"Rocking Horse Trading Co.   |   {document.page}")
        canvas.restoreState()

    cells = [[Paragraph(escape(label), header) for label in headings]]
    cells.extend([
        [Paragraph(escape(value).replace("\n", "<br/>"), body) for value in row]
        for row in rows
    ])
    table = LongTable(cells, colWidths=[49, 76, 49, 50, 62, 56, 66, 66, 240],
                      repeatRows=1, splitInRow=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), ink),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LINEBELOW", (0, 0), (-1, 0), 1, gold),
        ("LINEBELOW", (0, 1), (-1, -1), .35, colors.lightgrey),
    ]))
    story = [Paragraph(escape(summary), body)]
    if note:
        story.append(Paragraph(f"Totals exclude missing values ({escape(note)}).", body))
    story.extend([Spacer(1, 10), table])
    doc.build(story, onFirstPage=decorate, onLaterPages=decorate)
    return output.getvalue()
