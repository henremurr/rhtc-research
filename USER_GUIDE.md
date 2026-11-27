# RHTC Three Peaks Research Platform — User Guide

**For:** RHTC internal research users<br>
**Stable release:** v2026.11.22<br>
**Last checked:** November 22, 2026
**Documentation update:** November 27, 2026 (Prediction Market Intelligence supplement)<br>
**Application:** Covered Call Screener / Income Engine and RHTC News Feed

## Table of contents

1. [Overview](#overview)
2. [Stable release baseline](#stable-release-baseline)
3. [Sign in and navigate](#sign-in-and-navigate)
4. [Manage watchlist data](#manage-watchlist-data)
5. [Use the Income Engine](#use-the-income-engine)
6. [Analyze stocks and calls](#analyze-stocks-and-calls)
7. [Use the news feed](#use-the-news-feed)
8. [Create transcripts and publish to YouTube](#create-transcripts-and-publish-to-youtube)
9. [Project inventory](#project-inventory)
10. [Other controls and settings](#other-controls-and-settings)
11. [Troubleshooting and data limitations](#troubleshooting-and-data-limitations)
12. [Customize and synchronize the dashboard menu](#customize-and-synchronize-the-dashboard-menu)
13. [Import brokerage CSV files](#import-brokerage-csv-files)
14. [Preview, print, and save financial reports](#preview-print-and-save-financial-reports)
15. [Transaction report](#transaction-report)
16. [Tax lot and ticker tax lot reports](#tax-lot-and-ticker-tax-lot-reports)
17. [Weekly income reports](#weekly-income-reports)
18. [Open tax lot report](#open-tax-lot-report)
19. [Cash Activity Report](#cash-activity-report)
20. [Reporting troubleshooting and limitations](#reporting-troubleshooting-and-limitations)
21. [Prediction Market Intelligence](#prediction-market-intelligence)

## Overview

The dashboard combines a shared RHTC research watchlist, a covered-call screening view, company and call research, and a saved news feed. It is a research and tracking tool. It does not submit orders to a brokerage.

Use the two view icons in the toolbar to switch between **Covered Call Screener / Income Engine** and **RHTC News**. The Income Engine toolbar, filters, and quote controls are hidden in News view so the news page has room to read and scroll.

The three research peaks are:

- **AI/I** — AI and infrastructure
- **EFM/I** — energy, fuels, and infrastructure
- **DS/I** — defense, security, and space

**Other** is available for symbols and news outside those themes. **Cross-Peak** is a news classification for stories spanning multiple themes.

The header shows the watchlist universe size, calls to review, median bid yield, and the time of the most recent quote refresh. A theme button switches between dark and light appearance. Use **Log out** to end the session.

## Stable release baseline

**v2026.11.22** is the current approved stable production baseline. The previous stable release **v2026.11.15** remains preserved for historical comparison. It covers the deployed Income Engine, shared watchlist and saved reports, stock and call scoring, Buffett and CEO-risk reports, earnings and split-aware price scenarios, news analysis, YouTube/X publishing controls, mobile layouts, comprehensive HTML/PDF reports, and the Infrastructure Audit.

The Git reference `stable/v2026.11.22` identifies the current stable source baseline, including the reporting and menu enhancements documented below. The historical reference `stable/v2026.11.15` remains unchanged. Future changes should be compared with the current stable branch before promotion. Application data remains outside Git and must be backed up separately. Application data remains in the configured persistent Railway volume and is not stored inside the source baseline.

## Sign in and navigate

Open the dashboard URL and enter the dashboard password. The dashboard requires a server-configured password; sessions last up to seven days unless the password is changed or you log out.

On phones, the page is designed to scroll as a single page. Full-screen controls are available in analysis and quote dialogs. Use their close button to return to the feed or screener. If the browser’s own bottom toolbar covers content, scroll the page itself rather than a nested panel.

| Control | What it does |
| --- | --- |
| Screener logo | Opens the Income Engine / covered-call screen |
| News logo | Opens the RHTC News Feed and hides Income Engine controls |
| Dashboard menu (☰) | Opens Reporting, Documentation, Connect to YouTube, Infrastructure audit, and other utilities. Choose **Customize menu** to reorganize or rename entries. |
| Theme button | Toggles dark and light themes |
| Log out | Ends the signed-in session |

## Manage watchlist data

Open **Watchlist Manager** from the Income Engine toolbar. The manager edits the shared server-side RHTC list, so a saved change is available to other signed-in browsers using the same deployment.

### Add a symbol

Fill in the ticker and choose a peak, then select the plus button. A ticker can appear more than once when it is assigned to different accounts, but cannot be duplicated for the same account.

The optional fields are:

| Field | Use |
| --- | --- |
| Share price | Manually tracked share price |
| Quantity | Manually tracked share count |
| Account | Brokerage/account label; selecting an account does not connect that brokerage |
| LT-Call | Long-term call strike or note |
| LT-Expy | Long-term call expiration in YYMMDD format |
| LT-Qty | Number of long-term calls |
| LT-Premium $ | Manually tracked premium amount |
| PG | A short page/group label for organizing rows |

These are user-maintained tracking fields. They are not imported or verified brokerage positions.

### Find, filter, sort, edit, or remove symbols

- **Find a ticker** narrows the displayed manager list as you type.
- **Filter** can show all symbols, holdings with share details, calls written, candidates for adding calls, rows with a PG value, an account, or a research peak.
- **Order by** sorts by PG/page, peak tier, expiration, or ticker.
- **Edit** opens a row’s fields. Choose **Save** to keep changes or **Cancel** to discard them.
- **Delete** removes that ticker/account row after a confirmation prompt.
- The manager totals summarize tracked call premium and position cost for the rows in the current view; they depend on the manually entered fields.

A browser-local watchlist from an older version may be offered for import. Use **Import symbols saved in this browser** only if that local list is the one you want to migrate into the shared list.

## Use the Income Engine

The screener estimates covered-call candidates for symbols in the watchlist.

### Main toolbar controls

| Control | What it does |
| --- | --- |
| **Refresh quotes** | Reloads the watchlist screen and updates the displayed quote timestamp. The regular button also requests an updated research note. |
| **Auto reload** | Refreshes the screen every 30 seconds, 1, 3, 5, 10, or 30 minutes. **Off** disables automatic refresh. The choice is remembered in this browser. |
| **Search ticker** | Filters the screener by ticker text. |
| **Peak / watchlist filter** | Shows all watchlist symbols, holdings, one of the three peaks, or Outside the Peaks. |
| **Stock / 5** and **Call / 5** | Choose **Missing** to focus on rows without a stock or call rating; **All** includes rated and unrated rows. |
| **Rows** | Limits the number of rows rendered: 10, 30, 60, 90, or All. |
| **Invest** | Sets the approximate maximum dollars allocated per 100-share call position. The suggested quantity is the whole-number count of 100-share units under Invest divided by the stock price. |
| **Order by** | Sorts by estimated income, combined RHTC score, stock score, call score, bid yield, expiration timing, open interest, implied volatility, or ticker. |

The **Previous / Next** controls page through expiration windows (such as 0–7 DTE). The screener chooses the nearest listed expiration on or after today and the closest out-of-the-money call above the share price for each symbol in the selected window.

### Read the screener columns

- **Ticker** opens the stock quote and covered-call detail dialog.
- **Peak** identifies the symbol’s assigned research group.
- **Stock** is the latest stock research rating, from 1 (Avoid) to 5 (Bargain).
- **Call** is the latest call-analysis rating, from 1 to 5.
- **RHTC** combines the stock and call scores for a quick comparison.
- **Last**, **Call contract**, **DTE**, **Qty**, and **Bid/Ask** describe the underlying quote and candidate contract.
- **Yield** is the call bid divided by the share price. It is a simple premium ratio, not a forecasted return.
- **Income** is an estimate using the bid/ask midpoint × 100 shares × suggested contract quantity.
- **Volume** and **OI/Vol** help assess option activity and liquidity.

Use the **Analyze stocks** and **Analyze calls** buttons above the table to analyze all currently displayed symbols or calls. These batch actions use current-source research and OpenAI API credits. Progress and per-symbol errors appear beside the buttons.

## Analyze stocks and calls

Select a ticker to open its quote and option details.

### Stock quote dialog

- **Analyze stock** requests a current-source company analysis, including a concise summary, detailed analysis, and available citations.
- **View reports** opens saved stock analyses with Previous/Next navigation and report deletion controls.
- **CEO Risk** opens the ticker's latest CEO-dependency and succession-risk assessment, or creates one when no saved assessment exists.
- **Print report** creates the comprehensive branded report and provides Open PDF, Download PDF, and Back to quote controls.
- The dialog can show company profile, fundamentals, quote statistics, prior and next earnings, and EPS estimates when optional data is available.
- The earnings section applies to every ticker. When valid inputs exist, it shows Cautious, Central, Optimistic, and Strong-beat next-quarter price scenarios. The Central case uses next-12-month EPS and a reasonable forward P/E; the Optimistic case holds the prior quarter's price/EPS multiple constant. Announced splits effective by the target date are shown with pre- and post-split targets.
- Select any pre-split price target to open its **13-week covered-call path**. Week N uses `last + N/13 × (target − last)`. Each row shows the seven-day path date, projected path price, nearest listed call expiration and strike, current bid/ask, and bid premium per contract. The premium is a current option-chain snapshot, not a forecast of what the option will trade for in that future week.
- Price scenarios are mechanical valuation cases, not predictions or personalized trade instructions. If current price, prior actual EPS, next-quarter EPS estimate, or usable next-12-month EPS is unavailable or unsuitable, the app does not invent a target.
- The stock rating and saved reports are stored with the shared watchlist.

### Buffett and CEO-risk reports

The Watchlist Manager includes saved Buffett-quality and CEO-risk scores and report actions. A score opens its latest report; a missing report can be generated from the ticker action. Report screens include navigation and deletion controls, and the manager provides filters for missing Buffett or CEO-risk work. These assessments are research aids and should be reviewed alongside the underlying filings and cited sources.

### Covered-call detail dialog

Use the expiration-window controls to inspect available candidate calls. **Analyze call** evaluates the displayed call screen, returns a cited research assessment when available, and stores the call score in the shared list.

### Deep ticker analysis

Use the ticker’s deep-analysis action where available to open a longer watchlist and Three Peaks impact analysis. The analysis dialog has:

- **Read analysis** (or Pause/Resume) for browser speech, and **Stop** to stop it.
- A close button and a full-screen toggle.
- A **Sources** list with links to cited material.
- **Create YouTube Transcript + MP3** to generate a spoken script and audio. See [Create transcripts and publish to YouTube](#create-transcripts-and-publish-to-youtube).

Research ratings and impact statements are analytical judgments, not price targets or personalized investment advice. Review the source links and quote freshness yourself.

## Use the news feed

Choose the News icon. The page contains saved stories and provides controls to search for new material.

### Feed controls

- **Peak** filters saved stories by All Peaks, AI/I, EFM/I, DS/I, Cross-Peak, or Other. It filters the stored feed; it does not initiate a new search.
- **Search stories or topic** filters saved story titles, source names, and excerpts as you type.
- **Search web** runs a fresh search for the entered topic and adds/deduplicates returned stories in the saved feed.
- **Scan for news** runs the standard current-news scan.
- The feed also runs an automatic scan daily at **6:00 a.m. Pacific**. The scan status shows the last recorded scan time.

Each story shows its peak, source, published date, retrieval time, headline, and source excerpt. Select the headline to open the original source in a new tab. Available story actions are:

| Story control | What it does |
| --- | --- |
| **Read excerpt** | Reads the headline and excerpt aloud; the same control pauses or resumes |
| **Stop** | Stops speech playback |
| **Translate to English** | Appears for a detected non-English story and reveals an English translation |
| **Analyze RHTC impact** | Opens a sourced analysis of the story’s potential impact on watchlist companies and the Three Peaks |
| **Publish** | Runs the automated analysis, transcript, audio, and YouTube upload flow; see the publishing warning below |
| **Post on X** | Posts the article headline, Three Peaks label, source link, and RHTC hashtags on X; a checkmark prevents accidental duplicate posts |

News search and analysis require the relevant server API keys. The story list is saved in the application database. The page displays all stories still stored there and has no date cutoff in the feed view.

## Create transcripts and publish to YouTube

There are two publishing paths. Check which one you are using before selecting a publish control.

### Reviewed analysis workflow

1. Open a news story with **Analyze RHTC impact** and wait for the analysis and citations to load.
2. Select **Create YouTube Transcript + MP3**.
3. Read the full generated transcript. You can use **Copy transcript**, **Download transcript**, or **Download MP3**, and play the audio in the built-in player.
4. Review and edit the video title and description, choose the RHTC series artwork, and set visibility.
5. Confirm that you reviewed the complete audio, title, description, and artwork.
6. Select **Publish to YouTube** and wait for the result link.

The series artwork options include AI & Infrastructure, Energy, Fuels & Infrastructure, Defense, Space & Infrastructure, Policy & Power, Think-Tank Watch, Three Peaks Audio Brief, and Pentagon Contract Watch.

**Visibility needs attention:** the current publishing form initially selects **Public**. Choose Private or Unlisted if that is what you intend before publishing. YouTube may still keep an API upload private if the Google API project has not passed the required audit.

### One-click story publishing

A story’s **Publish** button runs analysis, transcript generation, MP3 creation, themed MP4 conversion, and upload automatically. It currently requests **Public** visibility and does not pause for the manual transcript/title/artwork review checkbox. Use this only when you are ready for that automated public-publishing path. Review the story’s source and content before starting it.

### Requirements and limits

Publishing requires the YouTube OAuth settings and MP4 conversion support to be configured on the server. The upload accepts MP3 audio up to 100 MB. API credentials belong in the hosting environment, not in the browser or this repository. Google may restrict uploads to Private until its project audit is complete. Uploaded video links and actual visibility are reported when the upload finishes.

Posting on X requires an X Developer app with **Read and write** permission, funded API credits, and these Railway Variables: `X_API_KEY`, `X_API_SECRET`, `X_ACCESS_TOKEN`, and `X_ACCESS_TOKEN_SECRET`. If permissions are changed in the X Developer Console, regenerate the access token and secret afterward. The feed records the confirmed Post ID and disables the article's X button after a successful post.

Transcript and audio generation use OpenAI API credits; news analysis uses current web search. API usage may incur separate charges.

## Project inventory

Select **Infrastructure Audit** in the guide menu to open **Development & deployment inventory**. The inventory summarizes the approved release, live runtime, and integrations used by the app, including hosting/deployment, Python packages, persistent SQLite storage, Tradier, Finnhub company/earnings/split data, OpenAI, Perplexity, YouTube, X, and browser-loaded fonts.

- The top cards report the stable release, deployed commit when Railway supplies it, number of inventoried products, presence of core credentials, runtime version/source, last check time, and storage location.
- Each service card describes its role, API/version, whether required secret names are present, the responsible account owner, plan/cost notes, lifecycle risks, and reference links.
- **Recheck deployment** requests a fresh runtime/inventory check.

The inventory can report whether a named credential exists, but never reveals its secret value. It cannot verify provider account ownership, invoices, balances, exact billing plans, or account trial status. Pricing and lifecycle notes are reference information and may become outdated; follow the links for current terms.

## Other controls and settings

- **Connection Settings / Market data source** summarizes the quote provider and whether the app is in demo or configured mode. It does not expose or accept the API token.
- **Preview data only** means the screener is using illustrative samples, not live market quotes.
- **Snapshots** are stored in the current browser only. They are not shared with other browsers and may be lost if browser storage is cleared.
- The default Tradier connection is the sandbox. Sandbox quotes are delayed (about 15 minutes); configuring a token does not make the dashboard a live order-entry system.
- The source pill and footer identify the current data mode.

## Troubleshooting and data limitations

| Symptom | Check |
| --- | --- |
| Screener says Preview data only | A Tradier token is not configured on the server, or live quote access is unavailable. Treat sample values as illustrative. |
| News feed is unavailable | Confirm sign-in, then check that Perplexity is configured and the news API is responding. The News view needs this service even to load saved-feed metadata. |
| News filter shows no stories | Try All Peaks, clear the topic search, and check that stories have been scanned and stored. A peak filter only returns items classified under that exact label. |
| Analysis or transcript fails | Check OpenAI configuration, provider availability, and API usage limits. |
| YouTube controls report not configured | Check all three YouTube OAuth variables and MP4 conversion support in the deployment inventory. |
| Watchlist changes do not persist across deployments | The deployment needs a persistent data volume mounted at the configured data directory. |
| Values differ from a brokerage screen | Quotes may be delayed; share details, holdings, and long-term call fields are manually maintained. |

The screener selects a single nearest expiration and nearest out-of-the-money call per symbol for its candidate view. Its yield and income figures do not account for assignment, commissions, taxes, spread execution, existing positions, or opportunity cost. Verify the current contract, bid/ask spread, liquidity, and brokerage account before making any trade decision.

## Customize and synchronize the dashboard menu

Open the **☰ dashboard menu** in the header. The **Reporting** group contains brokerage importing and financial reports; **Documentation** contains Open User Guide, Update User Guide, Create PDF · View / Print, and Download PDF. Connect to YouTube and Infrastructure audit are available as separate actions.

To customize the menu:

1. Open ☰ and choose **Customize menu**.
2. Drag an entry to reorder or move it. On touch devices, use the **up/down** movement controls if dragging is inconvenient.
3. Select entries and choose **Group selected** to create a group.
4. Choose **Rename** for a menu entry or group; **Ungroup** removes an existing grouping.
5. Choose **Done** after making changes.

Multiple groups can remain expanded at once. Changing an entry's displayed name does not change its underlying report or screen. **Connect to YouTube** is maintained as a top-level entry, even when restoring a saved menu.

**Cross-device persistence:** the browser saves menu layout locally for immediate use and also sends it to the application's server. On load, a signed-in device requests the shared layout, allowing a consistent arrangement across iPhone, iPad, and desktop browsers using the same deployment. If the shared save fails or a device is offline, changes may remain local. Confirm the same deployment and reload the dashboard if layouts differ.

## Import brokerage CSV files

Open **Reporting → Import CSV files**. The importer loads brokerage-exported transaction histories into the application's persistent transaction database; it does **not** connect to a brokerage or submit orders.

| File format | Supported source | Account handling |
| --- | --- | --- |
| **Fidelity** | Fidelity brokerage transaction-history CSV | Enter the account identifier |
| **Fidelity IRA** | Fidelity Accounts History CSV | Leave Account ID blank to use numbers within the CSV, or provide one to import only its matching rows |
| **Schwab** | Schwab transaction CSV | Enter an account identifier; alphanumeric IDs are accepted |
| **Vanguard** | CSV matching the implemented Vanguard column layout | Enter the account identifier; export layouts may vary |

To import:

1. Export the trading history as a CSV from the brokerage.
2. Select its **File format** and specify Account ID when required.
3. Choose the source CSV and submit the import.
4. Review the import result, including skipped records.
5. Run a transaction report to reconcile dates, quantities, actions, and amounts against your brokerage statement.

Use the **same account identifier** in later imports for that account. The importer generates fingerprints for recognized records to avoid loading the same transaction twice when CSV date ranges overlap. It distinguishes brokerage/account histories instead of treating all files from one brokerage as a single account.

Account-specific history management must be scoped to the selected brokerage/account identity; never assume an account purge affects all accounts. Retain original statements and files for reconciliation. Supported formats require the expected export headers; a broker changing its CSV layout may require an importer update.

## Preview, print, and save financial reports

The financial reporting screens follow a **preview-first** workflow:

1. Open the report under **Reporting**.
2. Choose the available account, tax year, and other report-specific filters.
3. Select **Preview report**; report rows remain hidden until requested.
4. Review the report, use **Full screen** if needed, or navigate back to the filters.
5. Use the PDF, print, save, and return controls appropriate to the browser.

The interface offers **Print or save PDF** on supported Apple mobile devices through system sharing. Desktop browsers may present separate print and download actions. A generated PDF is a separate snapshot of the selected report. Use **Return to dashboard** or the report navigation controls instead of relying on the browser's back button.

Financial PDFs use RHTC-branded report headings, formatted tables, and page-number footers; longer reports repeat report headings on subsequent pages where supported. Print/save behavior also depends on browser and operating-system permissions.

## Transaction report

Open **Reporting → Transaction report** and select an account and reporting year. The report organizes imported stock and option transaction records by underlying ticker and shows **Date, Action, Security, Quantity, Price ($), and Amount ($)**. Ticker groups provide grouped details and open-position summaries where applicable.

The report uses transaction quantities—not dollar balances—to determine whether a stock or option position remains open. It distinguishes stock buys/sells from written or repurchased calls and applies ordering rules for activities occurring on the same day (including purchases before relevant sales). Use it to reconcile purchases, disposals, and closing trades. Option contracts may be represented with a leading hyphen in ticker-based views.

The report is a reconstruction from imported history, not an independently verified current brokerage position statement. Missing opening history, assignments, exercises, or corporate actions can affect remaining-position calculations.

## Tax lot and ticker tax lot reports

### Tax Lot Report — Form 8949 presentation

Open **Reporting → Tax lot report · Form 8949**, select an account and tax year, and choose **Preview report**. Completed transactions are matched using **FIFO (first in, first out)** against the available full account history. Open or unmatched tax lots are omitted.

The report follows the principal **IRS Form 8949** column structure:

| Column | Content |
| --- | --- |
| (a) | Description of property |
| (b) | Date acquired |
| (c) | Date sold or disposed |
| (d) | Proceeds |
| (e) | Cost or other basis |
| (f) | Adjustment code |
| (g) | Adjustment amount |
| (h) | Gain or loss |

Short-term (held one year or less) and long-term (held more than one year) transactions appear in separate sections, followed by proceeds, basis, and net gain/loss totals for each holding-period category.

### Ticker Tax Lot Report

Open **Reporting → Ticker tax lot report · Form 8949** and select an account, tax year, and underlying ticker from the dropdown. The selectable ticker list omits leading-hyphen option symbols, but the related option activity remains eligible for the report for that underlying ticker. For example, selecting **AAOI** may include transactions represented as **AAOI** and **-AAOI**.

**Tax caveat:** this is an analytical report, **not an official IRS filing**. Reconcile imported cost basis, option assignments/exercises, wash sales, adjustments, corporate actions, and broker-issued Form 1099-B records before filing.

## Weekly income reports

Both reports select an **account and tax year** and group **completed tax lots by closing week**. These are realized-lot measures and should not be equated automatically with the cash premium received on the date an option was written.

### Weekly Income Summary Report

Open **Reporting → Weekly Income Summary Report**. The report shows each reported week, date range, number of closed lots, **Proceeds, Cost basis, and Net gain/loss**, followed by a total row. Weeks without completed lots may be absent rather than displayed as zero-income weeks.

### Weekly Income Detail Report

Open **Reporting → Weekly Income Detail Report** to expand the summary by tax-lot records. Each week shows acquisition and sale dates, proceeds, basis, code, adjustments, and net gain/loss. Related stock and option records are organized by underlying ticker within each week, with **lightly shaded ticker subtotal rows**. Use the detail to explain which completed positions contributed to each week's result.

## Open tax lot report

Open **Reporting → Open tax lot report** and choose an account and reporting year (or **All/latest**, when offered). This lists positions remaining unmatched at the selected cutoff rather than trades already closed in the Form 8949 report.

Visible columns include **Ticker / security, Side, Date acquired, Holding period, Open quantity, Cost/Premium, and Per unit**. Entries are grouped by underlying ticker and acquisition date, with shares before associated option-contract positions. Stock positions and individual option-security groups have their own subtotal lines.

- **Long stock:** cost is displayed using a negative cash-flow convention. **Total Long** summarizes open shares, aggregate cost, and average cost per share.
- **Short written calls:** collected premium is positive. The option **Per unit** premium is total remaining premium ÷ (**open contracts × 100**) for standard 100-share contracts. **Total Short** summarizes open contracts, total premium, and average premium per underlying share for each option-security group.
- Subtotals are **lightly shaded**, remain with the corresponding security group, and are not merely grand totals at the end of the report.
- Cash-sweep symbols such as **FCASH** are excluded from the open stock-lot presentation. Expired calls and assigned calls are processed by the closing/assignment matching logic instead of being shown as still-open contracts.

Verify lot dates, quantities, assigned/expired contract treatment, premiums, and any nonstandard contract deliverables against brokerage records.

## Cash Activity Report

Open **Reporting → Cash Activity Report**. Select brokerage/account filters and choose **Preview report** to view **non-stock and non-option cash movements**.

Recognized activity may include deposits, withdrawals, transfers in/out, dividends and distributions, federal tax withholding/payments, **interest earned**, **margin interest**, **bill payments**, **cash advances**, and other classified cash activities. Interest earned and margin interest have separate categories; bill pay and cash advance are also separate.

Within each category, entries are organized by date and show **Date, Transaction, Ticker, Description, and Amount** with a **category subtotal**. Use the report to reconcile cash inflows, outflows, charges, and distributions separately from security transactions. The accuracy of categorization depends on the imported broker action codes and descriptions.

## Reporting troubleshooting and limitations

| Symptom | Check |
| --- | --- |
| No account choices appear | Import the appropriate CSV first; confirm account ID and supported headers. |
| Expected transactions are absent | Check the source export date range, brokerage format, account ID, and duplicate-skipping result. |
| A tax-lot report contains no rows | Confirm the selected year has **completed**, FIFO-matchable positions; open lots do not appear in Form 8949. |
| Open quantities or option positions look wrong | Reconcile buy/sell and written/repurchased call quantities, assignments, expirations, exercises, and earlier imported history. |
| Weekly income differs from cash premiums received | Compare closing dates against premium receipt dates; use Weekly Income Detail for lot-level reconciliation. |
| Cash activity is misclassified | Review the original CSV action and description; different brokers use different labels. |
| Menu layout differs across devices | Verify both browsers use the same signed-in deployment and that the server received the shared menu save. |
| Print or download does not work | Confirm that PDF generation succeeded, review browser permission prompts, and check iOS sharing/Files availability. |

All reporting results are derived from imported CSV records and application calculations. Missing transactions, broker-specific codes, rounding, historical cost-basis differences, wash sales, split adjustments, or options events can produce discrepancies. **Brokerage statements and official tax documents remain authoritative.**

### Release discipline

The current stable release is **v2026.11.22** at Git reference **`stable/v2026.11.22`**. The earlier **v2026.11.15** baseline remains available at **`stable/v2026.11.15`**. Promotion of future code requires a separate release decision and validation.


## Prediction Market Intelligence

Added to the main development branch on November 27, 2026, through PRs #263–266. This section documents the implementation and its intended analytical purpose; it does not promote the stable release or certify production runtime validation.

### Purpose and model influence

Prediction Market Intelligence adds a **forward-looking evidence layer** to RHTC research. Whereas financial statements describe business performance and news reports describe developments, prediction-market prices express what participants currently expect may occur. The system retrieves public Polymarket data for research only. It does not wager, connect wallets, submit brokerage orders, retrain underlying AI models, or change their parameters. Instead, selected market evidence is supplied as contextual input to existing report-generation models.

| RHTC model | Implementation status | Purpose |
| --- | --- | --- |
| News Summary | Integrated in source | Compare independently reported developments with changing market expectations. |
| The Long Game | Integrated in source | Evaluate strategic risks, emerging opportunities, and possible portfolio misalignment. |
| Stock Analysis | Proposed | Identify external catalysts and company-specific risks. |
| Buffett Model | Proposed, contextual only | Investigate threats to durable business economics and competitive advantages. |
| CEO Risk | Proposed | Investigate leadership, succession, and regulatory risks. |
| Covered Call Analysis | Proposed | Identify event risk within the recorded contract life. |
| RHTC Composite Score | Proposed | Consider corroborated forward-looking risks and opportunities without double-counting existing factors. |

Prediction-market evidence does **not currently directly change numerical stock, call, Buffett, CEO Risk, or composite scores**. News Summary and The Long Game receive selected evidence from completed saved scans, including market-implied probabilities, available historical changes, quality indicators, research hypotheses, recorded exposure, and confirmation requirements. The Long Game retains that context with the job inputs for reproducible historical analysis and checkpoint recovery.

### Research methodology

The analytical sequence is:

1. **Prediction Market Intelligence:** What might happen?
2. **Independent research:** What evidence supports or contradicts that expectation?
3. **Three Peaks thesis:** Which investment assumptions might strengthen or deteriorate?
4. **Portfolio impact assessment:** Which recorded holdings, industries, supply chains, and emerging companies could benefit or suffer?
5. **Strategic decision support:** Evaluate whether further research supports accumulation, maintenance, reduction, rebalancing, or waiting for confirmation.

Discovery is not restricted to the watchlist. It covers AI/I (AI and infrastructure), EFM/I (energy, fuels, manufacturing and infrastructure), DS/I (defense, security and space), Human Economy (needs, comfort, connection, experience, aspiration and well-being), macroeconomics, and markets outside established categories. Unclassified markets remain available for emerging-theme discovery.

The following examples are hypothetical, not live market readings or verified company recommendations.

| Changing market expectation | Potential research implications |
| --- | --- |
| Increased probability of semiconductor export restrictions | Reassess NVDA, AMD, MU and MRVL exposure. |
| Increased probability of nuclear regulatory reform | Investigate OKLO, SMR, LEU and nuclear supply chains. |
| Increased probability of expanded defense expenditure | Reassess LMT, NOC, KTOS, AVAV and emerging suppliers. |
| Increased probability of interest rate increases | Review margin exposure and capital-intensive growth businesses. |
| Increased probability of commercial fusion breakthroughs | Investigate infrastructure and component suppliers. |
| Increased probability of accelerated AI adoption | Investigate second-order beneficiaries in electricity, cooling, optical networking and memory. |

### Proposed Forward Intelligence Score (FIS)

A separate Forward Intelligence Score is recommended for future development rather than allowing prediction markets to distort fundamental scores. The following weights are illustrative and **not implemented**:

| Factor | Proposed weight |
| --- | ---: |
| Potential economic impact | 25% |
| Independent corroboration | 25% |
| Three Peaks strategic relevance | 20% |
| Market liquidity and credibility | 15% |
| Probability movement | 10% |
| Event proximity | 5% |

This proposed score is distinct from the existing semantic market relevance score (0–10). Probability movement alone would carry only 10% of the proposed weighting. Before implementing FIS, define factor scales, missing-evidence treatment, directional impact, validation and safeguards against double-counting correlated markets. Do not treat a high FIS as a buy or sell instruction.

### Using the research screen

Open **Dashboard menu → Other Reports → Prediction Market Intelligence** (location may differ in a customized menu). Filter by thesis or exposure, search markets and tickers, page through results, and inspect the resolution rules, liquidity, volume, bid-ask spread, relevance and candidate company associations. The Emerging filter includes candidates outside the watchlist and relevant markets without watchlist matches. Holdings are derived from the recorded watchlist quantities and account labels, not a reconciled brokerage statement.

**Refresh markets** requests discovery; **Reload results** reads saved results; **Print or save PDF** prints the displayed page; **Return to dashboard** navigates back. Partial results are explicitly identified and available during discovery. Report integrations use completed snapshots, not incomplete scans.

### Automated discovery, persistence and cost controls

The current implementation is designed to scan active, non-closed markets approximately every six hours using cursor pagination. Each retrieved page and its cursor are stored atomically in SQLite on persistent storage. Interrupted scans resume from a saved checkpoint where the provider cursor remains valid. Completed snapshots retain a rolling 35-day history. Historical 1-, 7- and 30-day comparisons require sufficiently close saved observations; unavailable comparisons are not fabricated.

A separate semantic research worker prioritizes economically relevant markets and reserves processing capacity for unclassified markets. Unchanged questions and resolution rules reuse cached analysis. Discovery is comprehensive by design, but semantic coverage is progressive and not guaranteed to be complete at any given time. AI usage is tracked by UTC day, with defaults of 100 requests and a 1,000,000-token threshold per day, and batches of up to 20 markets. A final request can exceed the token threshold; failed requests may have unknown usage. Estimated dollar costs require configured model pricing and are unavailable when usage is unknown.

### Interpretation and strategic safeguards

Market-implied probabilities are not objective forecasts. Thin liquidity, wide spreads, ambiguous resolution rules, correlated events, stale observations, concentrated participation and speculative behavior can distort them. AI-generated ticker associations and opportunity/risk descriptions are research hypotheses and require independent verification. Do not equate an increased probability with a particular security's expected return or use it as an isolated trading signal.

The strategic objective is to detect emerging investment opportunities and threats before they reach the watchlist, challenge existing assumptions, identify portfolio misalignment, and improve the timing of research, capital allocation and covered-call review. Independent evidence, business fundamentals, current valuation, liquidity, verified account exposure and contract details remain necessary for investment decisions.

**Validation status:** the implementation is merged into main, but complete live discovery, semantic processing, report integration and corrected mobile rendering have not been independently verified. The stable release baseline remains unchanged.
