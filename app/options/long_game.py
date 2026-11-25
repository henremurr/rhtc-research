"""Render the signed-in Long Game report from saved dashboard records."""

import json
from html import escape
from pathlib import Path
from string import Template
from urllib.parse import urlsplit


def html(value):
    return escape(str(value if value is not None else "—"))


def money(value):
    return "—" if value is None else f"${value:,.2f}"


def cell_row(*values):
    return "".join(f"<td>{html(value)}</td>" for value in values)


def link(url, label):
    try:
        parsed = urlsplit(url or "")
        if parsed.scheme in {"https", "http"} and parsed.hostname:
            return f'<a href="{html(url)}" target="_blank" rel="noopener noreferrer">{html(label)}</a>'
    except ValueError:
        pass
    return html(label)


def stock_details(record):
    label = f'{record["created_at"][:10]} · {record["rating_label"] or "Stock analysis"}'
    return (
        f"<details><summary>{html(label)}</summary>"
        f'<div class="report-text">{html(record["analysis_text"] or record["details"] or record["summary"])}</div></details>'
    )


def ceo_details(record):
    try:
        report = json.loads(record["report_json"])
    except (ValueError, TypeError):
        report = {}
    label = f'{record["created_at"][:10]} · {record["risk_rating"] or "CEO Risk"}'
    if record["risk_score"] is not None:
        label += f' · {record["risk_score"]:g}/100'
    factors = "".join(
        f'<li>{html(factor.get("dimension") or factor.get("name") or factor.get("factor") or "")} '
        f'{html(factor.get("evidence") or factor.get("assessment") or factor.get("rationale") or "")}</li>'
        for factor in report.get("factors", [])
    )
    scenarios = "".join(
        f'<li>{html(scenario.get("event"))} · {html(scenario.get("likely_effect"))} · {html(scenario.get("recovery_path"))}</li>'
        for scenario in report.get("scenarios", [])
    )
    signals = "".join(f"<li>{html(signal)}</li>" for signal in report.get("monitor_signals", []))
    citations = "".join(
        f'<li>{link(citation.get("url"), citation.get("title") or citation.get("url"))}</li>'
        for citation in report.get("citations", [])
    )
    return (
        f"<details><summary>{html(label)}</summary><p>{html(report.get('ceo_name'))} · "
        f"{html(report.get('summary'))}</p>"
        + "".join(f"<h4>{name}</h4><ul>{items}</ul>" for name, items in
                  (("Factors", factors), ("Scenarios", scenarios), ("Monitor signals", signals), ("Sources", citations)) if items)
        + "</details>"
    )


def render_long_game(watchlist, stock, ceo, news, timestamp):
    tickers = sorted({row["symbol"] for row in watchlist})
    by_ticker = {ticker: [] for ticker in tickers}
    for row in watchlist:
        by_ticker[row["symbol"]].append(row)
    positions, research = [], []
    for ticker, entries in by_ticker.items():
        holdings = [entry for entry in entries if (entry["quantity"] or 0) > 0]
        for entry in holdings or entries[:1]:
            calls = [entry, *entry["additional_calls"]]
            details = []
            for call in calls:
                if not any(call.get(field) not in (None, "") for field in ("lt_call", "lt_expy", "lt_qty", "lt_premium")):
                    continue
                expiry = call.get("lt_expy") or "—"
                if len(expiry) == 6 and expiry.isdecimal():
                    expiry = f"20{expiry[:2]}-{expiry[2:4]}-{expiry[4:]}"
                details.append(
                    f'Strike {html(call.get("lt_call") or "—")} · Exp. {html(expiry)} · '
                    f'{html(call.get("lt_qty"))} contracts · {money(call.get("lt_premium"))}'
                )
            shares = entry["quantity"] if holdings else None
            cost = shares * entry["share_price"] if shares is not None and entry["share_price"] is not None else None
            row = cell_row(ticker, entry["peak"], (entry["account"] or "No account") if holdings else "Watchlist only",
                           f"{shares:,g}" if shares is not None else "—", money(entry["share_price"]) if holdings else "—", money(cost))
            positions.append("<tr>" + row + "<td>" + ("<br>".join(details) or "—") + "</td></tr>")
        stock_reports = stock.get(ticker, [])
        ceo_reports = ceo.get(ticker, [])
        research.append(
            f'<details><summary>{html(ticker)} · {len(stock_reports)} stock analyses · {len(ceo_reports)} CEO Risk reports</summary>'
            '<div class="research"><section><h3>Saved stock analysis</h3>'
            + ("".join(map(stock_details, stock_reports)) or "<p>No saved stock analysis.</p>")
            + "</section><section><h3>Saved CEO Risk</h3>"
            + ("".join(map(ceo_details, ceo_reports)) or "<p>No saved CEO Risk report.</p>")
            + "</section></div></details>"
        )

    articles = "".join(
        f'<li>{link(article["url"], article["title"])} <small>{html(article["source"])} · '
        f'{html((article["published_at"] or article["first_seen_at"])[:10])} · {html(article["peak"])}</small>'
        f'<div>{html(article["snippet"] or "")}</div></li>'
        for article in news
    )
    template = (Path(__file__).parent / "templates" / "long_game.html").read_text(encoding="utf-8")
    return Template(template).substitute(
        timestamp=html(timestamp), positions="".join(positions) or '<tr><td colspan="7">The watchlist is empty.</td></tr>',
        ticker_count=len(tickers), research="".join(research), news_count=len(news),
        articles=articles or "<li>No saved articles.</li>",
    )
