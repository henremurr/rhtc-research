from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter()

_STYLE = """
:root{color-scheme:light;--ink:#171717;--gold:#b68a2f;--paper:#fbfaf7;--muted:#625f58}
*{box-sizing:border-box}
body{margin:0;background:var(--paper);color:var(--ink);font:16px/1.7 Georgia,"Times New Roman",serif}
header,main,footer{max-width:900px;margin:0 auto;padding:24px}
header{display:flex;align-items:center;justify-content:space-between;border-bottom:1px solid #d8c79f}
.brand{font:bold 18px/1.2 Arial,sans-serif;letter-spacing:.12em;color:var(--ink);text-decoration:none}
.brand span{color:var(--gold)}
nav{display:flex;gap:18px;flex-wrap:wrap}
nav a,footer a{color:var(--ink);text-decoration-color:var(--gold);text-underline-offset:4px}
main{padding-top:58px;padding-bottom:68px}
.eyebrow{color:var(--gold);font:bold 12px Arial,sans-serif;letter-spacing:.18em;text-transform:uppercase}
h1{font-size:clamp(34px,7vw,54px);line-height:1.12;margin:12px 0 18px}
h2{font-size:23px;margin:32px 0 8px}
p,li{max-width:74ch}
.lead{font-size:20px;color:#38352f}
.button{display:inline-block;margin-top:14px;padding:11px 18px;background:var(--ink);color:white;text-decoration:none;border-radius:4px;font:600 14px Arial,sans-serif}
footer{border-top:1px solid #e2ded5;color:var(--muted);font:13px Arial,sans-serif;padding-top:20px;padding-bottom:30px}
@media(max-width:600px){header{align-items:flex-start;gap:18px;flex-direction:column}main{padding-top:38px}}
"""

def _page(title: str, body: str) -> HTMLResponse:
    html = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="description" content="RHTC Dashboard App — Three Peaks research, options screening, news analysis, and user-directed YouTube publishing.">
<title>{title} | RHTC Dashboard App</title>
<style>{_STYLE}</style>
</head>
<body>
<header>
  <a class="brand" href="/about" aria-label="RHTC Dashboard home">RHTC <span>◆</span></a>
  <nav aria-label="Main navigation">
    <a href="/about">About</a><a href="/privacy">Privacy</a><a href="/terms">Terms</a>
  </nav>
</header>
<main>{body}</main>
<footer>
  <div>Rocking Horse Trading Company · RHTC Dashboard App</div>
  <div>For support or privacy questions, use the support contact shown on the app’s Google OAuth consent screen.</div>
</footer>
</body>
</html>"""
    return HTMLResponse(content=html, headers={"Cache-Control": "public, max-age=300"})

_HOME = """
<p class="eyebrow">Rocking Horse Trading Company</p>
<h1>RHTC Dashboard App</h1>
<p class="lead">A private research dashboard for organizing market and news information through RHTC’s Three Peaks framework: AI/I, EFM/I, and DS/I.</p>
<p>The dashboard brings together watchlist and options screening, stock and company research, news analysis, and saved reports. It also lets an authorized user prepare and publish selected audio and video briefings to the user’s connected YouTube channel.</p>
<p>Publishing is initiated by the user. The user chooses the video title, description, and visibility before an upload is sent to YouTube.</p>
<p>RHTC research is for informational and educational purposes. It is not individualized investment advice, and the dashboard does not place trades.</p>
<a class="button" href="/options/">Open dashboard sign-in</a>
"""

_PRIVACY = """
<p class="eyebrow">Effective November 11, 2026</p>
<h1>Privacy Policy</h1>
<p class="lead">This policy explains how the RHTC Dashboard App handles information, including Google and YouTube data, when you use the app.</p>

<h2>Information you provide</h2>
<p>The app processes information you enter or upload, such as article links or text, research requests, video titles and descriptions, and MP3 audio selected for a briefing. The dashboard also stores research and news records needed to provide its features.</p>

<h2>Google and YouTube data</h2>
<p>The app uses Google OAuth credentials configured by the app administrator on the server. When you request an authorization check, the app exchanges its server-side refresh token for a short-lived access token and may read the connected YouTube channel’s title to confirm which channel is connected. When you choose to publish, the app sends the selected video, title, description, artwork, and visibility setting to YouTube.</p>
<p>The app uses YouTube data only to verify the connected channel and complete the YouTube action you request. It does not use Google user data for advertising, sell it, or use it to train machine-learning models. The app does not request access to Gmail, Google Drive, or contacts.</p>

<h2>Storage and retention</h2>
<p>The OAuth client credentials and refresh token are configured as server-side Railway service variables. The app does not put those credentials in the browser or its research database. Short-lived access tokens are used by the server for the requested YouTube operation. Uploaded MP3 files are processed in a temporary server directory and removed when that request finishes.</p>
<p>If you publish a briefing from a news item, the app stores the resulting YouTube video ID, video link, and visibility status with that item. News-feed records are currently retained for up to 90 days. Other saved research records remain in the dashboard until they are deleted or purged using the app’s available controls.</p>

<h2>When information is shared</h2>
<p>Information is sent to Google and YouTube when needed to authorize or complete a YouTube action you request. Railway hosts the app and its server-side configuration. The app does not sell Google user data or share it with advertisers.</p>

<h2>Your choices</h2>
<p>You control whether to request a channel check or publish a video and choose the video’s visibility setting. You can revoke the app’s Google access in your Google Account’s third-party connections. Revoking access prevents future YouTube checks and uploads until authorization is restored.</p>

<h2>Security</h2>
<p>OAuth credentials are kept in server-side service configuration and are not intentionally exposed to the browser. No internet service can guarantee absolute security; contact the app administrator if you believe your account or authorization has been misused.</p>

<h2>Changes and contact</h2>
<p>This policy may be updated when the app’s features or data practices change. For privacy questions or requests, use the support contact shown on the RHTC Dashboard App’s Google OAuth consent screen.</p>
"""

_TERMS = """
<p class="eyebrow">Effective November 11, 2026</p>
<h1>Terms of Service</h1>
<p class="lead">These terms govern access to the RHTC Dashboard App, operated for Rocking Horse Trading Company (“RHTC”). By using the app, you agree to these terms.</p>

<h2>Purpose and permitted use</h2>
<p>The app provides research and information tools, including watchlist and options screening, stock and news analysis, saved reports, and user-directed YouTube briefing publication. Use it only for lawful purposes and only if you are authorized to access the dashboard.</p>

<h2>Research is informational</h2>
<p>App content is provided for informational and educational purposes only. It is not financial, investment, tax, or legal advice, and it is not a recommendation to buy or sell any security. The app does not execute trades. Information may be incomplete, delayed, or inaccurate; verify important information independently and make your own decisions.</p>

<h2>YouTube publishing</h2>
<p>You are responsible for the audio, artwork, title, description, and other material you submit, including having the rights and permissions needed to use it. You choose the video’s visibility and are responsible for reviewing it before publication. Uploads are subject to Google and YouTube terms, policies, and availability.</p>

<h2>Availability and third-party services</h2>
<p>RHTC may change, suspend, or discontinue app features. The app depends on third-party providers, including Google/YouTube and hosting services, whose services are governed by their own terms. RHTC does not guarantee uninterrupted access or the availability of those services.</p>

<h2>Disclaimer</h2>
<p>The app is provided on an “as available” basis to the extent permitted by law. RHTC makes no promise that the app or its research output will meet every user’s needs or be free of errors.</p>

<h2>Contact</h2>
<p>For questions about these terms, use the support contact shown on the RHTC Dashboard App’s Google OAuth consent screen.</p>
"""

@router.get("/about", response_class=HTMLResponse, include_in_schema=False)
async def about_page() -> HTMLResponse:
    return _page("About", _HOME)

@router.get("/privacy", response_class=HTMLResponse, include_in_schema=False)
async def privacy_page() -> HTMLResponse:
    return _page("Privacy Policy", _PRIVACY)

@router.get("/terms", response_class=HTMLResponse, include_in_schema=False)
async def terms_page() -> HTMLResponse:
    return _page("Terms of Service", _TERMS)
