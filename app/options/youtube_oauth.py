"""Dashboard-owned YouTube authorization; secrets never enter browser responses."""
from __future__ import annotations

import base64
import hashlib
import html
import os
import secrets
import sqlite3
import time
from contextlib import contextmanager
from urllib.parse import urlencode, urlsplit

import httpx
from cryptography.fernet import Fernet, InvalidToken
from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app.options.news import db_path

router = APIRouter(prefix="/api/youtube", tags=["youtube"])
SCOPE = "https://www.googleapis.com/auth/youtube.upload"
COOKIE = "rhtc_youtube_oauth"


@contextmanager
def database():
    with sqlite3.connect(db_path(), timeout=15) as db:
        db.execute("CREATE TABLE IF NOT EXISTS youtube_connection (id INTEGER PRIMARY KEY CHECK(id=1), token TEXT NOT NULL)")
        db.execute("CREATE TABLE IF NOT EXISTS youtube_oauth_state (state TEXT PRIMARY KEY, browser TEXT NOT NULL, verifier TEXT NOT NULL, expires REAL NOT NULL)")
        yield db


def cipher():
    secret = os.getenv("YOUTUBE_CLIENT_SECRET", "")
    if not secret:
        raise HTTPException(503, "YouTube client secret is not configured.")
    return Fernet(base64.urlsafe_b64encode(hashlib.sha256(secret.encode()).digest()))


def saved_refresh_token():
    with database() as db:
        row = db.execute("SELECT token FROM youtube_connection WHERE id=1").fetchone()
    if row:
        try:
            return cipher().decrypt(row[0].encode()).decode()
        except InvalidToken:
            raise HTTPException(503, "YouTube connection needs to be renewed after a credential change.")
    return os.getenv("YOUTUBE_REFRESH_TOKEN", "")


def base(request):
    return str(request.scope.get("root_path", "")).rstrip("/") or "/options"


def redirect_uri():
    uri = os.getenv("YOUTUBE_REDIRECT_URI", "").strip()
    if not uri and os.getenv("RAILWAY_PUBLIC_DOMAIN"):
        uri = "https://" + os.environ["RAILWAY_PUBLIC_DOMAIN"].strip().rstrip("/") + "/options/api/youtube/callback"
    parsed = urlsplit(uri)
    if parsed.scheme != "https" or not parsed.netloc or parsed.query or parsed.fragment or not parsed.path.endswith("/api/youtube/callback"):
        raise HTTPException(503, "Set YOUTUBE_REDIRECT_URI to this dashboard's HTTPS callback URL and register it in Google Cloud.")
    return uri


def page(request, message=""):
    callback = str(request.url_for("youtube_callback")).replace("http://", "https://", 1)
    setup_error = ""
    try:
        callback = redirect_uri()
    except HTTPException as exc:
        setup_error = str(exc.detail)
    configured = not setup_error and all(os.getenv(k) for k in ("YOUTUBE_CLIENT_ID", "YOUTUBE_CLIENT_SECRET"))
    if not message and setup_error:
        message = "YouTube connection setup is incomplete. Follow the steps below; you can still return to the dashboard."
    with database() as db:
        connected = bool(db.execute("SELECT 1 FROM youtube_connection WHERE id=1").fetchone())
    prefix = html.escape(base(request), quote=True)
    status = "YouTube connected through this dashboard." if connected else "Connect the YouTube channel used for RHTC publishing."
    csrf = secrets.token_urlsafe(32)
    response = HTMLResponse(f'''<!doctype html><html lang="en"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Connect YouTube · RHTC</title><body style="font:18px system-ui;max-width:760px;margin:50px auto;padding:24px"><h1>Connect YouTube</h1><p role="status">{html.escape(message or status)}</p><p>This connection allows RHTC to upload videos to the channel you authorize. Publishing still requires your confirmation in the dashboard.</p><form method="post" action="{prefix}/api/youtube/connect"><input type="hidden" name="csrf" value="{csrf}"><button {'disabled' if not configured else ''} style="padding:14px;font:inherit">{'Reconnect' if connected else 'Connect'} YouTube</button></form><details {'open' if not configured else ''}><summary>Connection setup</summary><p>In Google Cloud, open the web application's OAuth client and add this Authorized redirect URI. Set Railway's YOUTUBE_REDIRECT_URI to the same value:</p><code style="overflow-wrap:anywhere">{html.escape(callback)}</code><p>YOUTUBE_CLIENT_ID and YOUTUBE_CLIENT_SECRET must belong to that client. RHTC_DATA_DIR must use persistent storage. The refresh token is saved automatically; no manual token copying is needed.</p></details><p><a href="{prefix}/">Return to dashboard</a></p></body></html>''', headers={"Cache-Control": "no-store", "Referrer-Policy": "no-referrer"})

    response.set_cookie("rhtc_youtube_form", csrf, max_age=600, httponly=True, secure=True, samesite="strict", path=base(request) + "/api/youtube")
    return response


@router.get("/connect")
def youtube_connection_page(request: Request):
    return page(request)


@router.post("/connect")
def youtube_connect(request: Request, csrf: str = Form("")):
    try:
        uri = redirect_uri()
    except HTTPException:
        return page(request, "The callback setting is missing or invalid. Use the HTTPS URL below in Google Cloud and Railway, then try again.")
    # A top-level form POST must originate from this dashboard.
    expected = urlsplit(uri)
    origin = request.headers.get("origin")
    form_cookie = request.cookies.get("rhtc_youtube_form", "")
    if not csrf or not form_cookie or not secrets.compare_digest(csrf, form_cookie) or (origin not in (None, "null", f"{expected.scheme}://{expected.netloc}")):
        raise HTTPException(403, "Start the connection from the dashboard.")
    if not os.getenv("YOUTUBE_CLIENT_ID") or not os.getenv("YOUTUBE_CLIENT_SECRET"):
        raise HTTPException(503, "Configure the YouTube OAuth client first.")
    state, browser, verifier = secrets.token_urlsafe(32), secrets.token_urlsafe(32), secrets.token_urlsafe(48)
    with database() as db:
        db.execute("DELETE FROM youtube_oauth_state WHERE expires < ?", (time.time(),))
        db.execute("INSERT INTO youtube_oauth_state VALUES (?, ?, ?, ?)", (state, hashlib.sha256(browser.encode()).hexdigest(), verifier, time.time() + 600))
    params = dict(client_id=os.environ["YOUTUBE_CLIENT_ID"], redirect_uri=uri, response_type="code", scope=SCOPE, access_type="offline", prompt="consent select_account", state=state, code_challenge=base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("="), code_challenge_method="S256")
    response = RedirectResponse("https://accounts.google.com/o/oauth2/v2/auth?" + urlencode(params), status_code=303)
    response.set_cookie(COOKIE, browser, max_age=600, httponly=True, secure=True, samesite="lax", path=base(request) + "/api/youtube")
    # Allow the existing signed dashboard session on Google's top-level return.
    # Its original signed expiry is still enforced by the dashboard middleware.
    from app.options.api import DASHBOARD_SESSION_COOKIE, DASHBOARD_SESSION_TTL
    session = request.cookies.get(DASHBOARD_SESSION_COOKIE)
    if session:
        response.set_cookie(DASHBOARD_SESSION_COOKIE, session, max_age=DASHBOARD_SESSION_TTL, httponly=True, secure=True, samesite="lax", path=base(request))
    response.headers["Cache-Control"] = "no-store"
    return response


@router.get("/callback", name="youtube_callback")
async def youtube_callback(request: Request):
    state = request.query_params.get("state", "")
    browser = request.cookies.get(COOKIE, "")
    with database() as db:
        db.execute("BEGIN IMMEDIATE")
        row = db.execute("SELECT browser, verifier, expires FROM youtube_oauth_state WHERE state=?", (state,)).fetchone()
        if not row or not browser or not secrets.compare_digest(row[0], hashlib.sha256(browser.encode()).hexdigest()) or row[2] < time.time():
            raise HTTPException(400, "YouTube connection expired or could not be validated. Start again from the menu.")
        db.execute("DELETE FROM youtube_oauth_state WHERE state=?", (state,))
    message = "YouTube connection was cancelled. Your existing connection has been kept."
    if not request.query_params.get("error"):
        code = request.query_params.get("code")
        if not code:
            return page(request, "Google returned no authorization code. Start again.")
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                result = await client.post("https://oauth2.googleapis.com/token", data=dict(client_id=os.environ["YOUTUBE_CLIENT_ID"], client_secret=os.environ["YOUTUBE_CLIENT_SECRET"], code=code, redirect_uri=redirect_uri(), grant_type="authorization_code", code_verifier=row[1]))
            payload = result.json() if result.status_code == 200 else {}
            if SCOPE not in str(payload.get("scope", "")).split() or not payload.get("refresh_token"):
                return page(request, "Google did not grant offline YouTube upload access. Please reconnect and allow the requested permission.")
            encrypted = cipher().encrypt(payload["refresh_token"].encode()).decode()
            with database() as db:
                db.execute("INSERT OR REPLACE INTO youtube_connection VALUES (1, ?)", (encrypted,))
        except (httpx.HTTPError, ValueError):
            return page(request, "Could not complete the connection with Google. Please try again.")
        response = RedirectResponse(base(request) + "/?youtube=connected", status_code=303)
    else:
        response = page(request, message)
    response.delete_cookie(COOKIE, path=base(request) + "/api/youtube")
    response.headers["Cache-Control"] = "no-store"
    response.headers["Referrer-Policy"] = "no-referrer"
    return response
