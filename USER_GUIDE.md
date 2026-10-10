# RHTC Three Peaks Research Platform — User Guide

**For:** RHTC internal research users  
**Last checked:** October 10, 2026  
**Application:** Covered Call Screener / Income Engine and RHTC News Feed

## Table of contents

1. [Overview](#overview)
2. [Sign in and navigate](#sign-in-and-navigate)
3. [Manage watchlist data](#manage-watchlist-data)
4. [Use the Income Engine](#use-the-income-engine)
5. [Analyze stocks and calls](#analyze-stocks-and-calls)
6. [Use the news feed](#use-the-news-feed)
7. [Create transcripts and publish to YouTube](#create-transcripts-and-publish-to-youtube)
8. [Project inventory](#project-inventory)
9. [Other controls and settings](#other-controls-and-settings)
10. [Troubleshooting and data limitations](#troubleshooting-and-data-limitations)

## Overview

The dashboard combines a shared RHTC research watchlist, a covered-call screening view, company and call research, and a saved news feed. It is a research and tracking tool. It does not submit orders to a brokerage.

Use the two view icons in the toolbar to switch between **Covered Call Screener / Income Engine** and **RHTC News**. The Income Engine toolbar, filters, and quote controls are hidden in News view so the news page has room to read and scroll.

The three research peaks are:

- **AI/I** — AI and infrastructure
- **EFM/I** — energy, fuels, and infrastructure
- **DS/I** — defense, security, and space

**Other** is available for symbols and news outside those themes. **Cross-Peak** is a news classification for stories spanning multiple themes.

The header shows the watchlist universe size, calls to review, median bid yield, and the time of the most recent quote refresh. A theme button switches between dark and light appearance. Use **Log out** to end the session.

## Sign in and navigate

Open the dashboard URL and enter the dashboard password. The dashboard requires a server-configured password; sessions last up to seven days unless the password is changed or you log out.

On phones, the page is designed to scroll as a single page. Full-screen controls are available in analysis and quote dialogs. Use their close button to return to the feed or screener. If the browser’s own bottom toolbar covers content, scroll the page itself rather than a nested panel.

| Control | What it does |
| --- | --- |
| Screener logo | Opens the Income Engine / covered-call screen |
| News logo | Opens the RHTC News Feed and hides Income Engine controls |
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
| **Max Spend** | Sets the approximate maximum dollars allocated per 100-share call position. The suggested quantity is the whole-number count of 100-share units under Max Spend divided by the stock price. |
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
- The dialog can show company profile and fundamentals when that optional data is available.
- The stock rating is stored with the shared watchlist.

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

Transcript and audio generation use OpenAI API credits; news analysis uses current web search. API usage may incur separate charges.

## Project inventory

Select **Infrastructure audit** in the Income Engine toolbar to open **Development & deployment inventory**. The inventory summarizes the live runtime and integrations used by the app, including hosting/deployment, Python packages, persistent SQLite storage, Tradier, optional Finnhub data, OpenAI, Perplexity, YouTube, and browser-loaded fonts.

- The top cards report the number of inventoried products, presence of core credentials, runtime version/source, last check time, and storage location when the service reports it.
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
