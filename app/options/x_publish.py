from __future__ import annotations

import base64
import hashlib
import hmac
import os
import secrets
import time
from typing import Any
from urllib.parse import quote, urlparse

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/x", tags=["x"])
CREATE_POST_URL = "https://api.x.com/2/tweets"
X_SETTINGS = ("X_API_KEY", "X_API_SECRET", "X_ACCESS_TOKEN", "X_ACCESS_TOKEN_SECRET")


class XPublishInput(BaseModel):
    title: str = Field(min_length=1, max_length=500)
    url: str = Field(min_length=8, max_length=2000)
    peak: str = Field(default="Other", max_length=30)


def missing_x_settings() -> list[str]:
    return [key for key in X_SETTINGS if not os.getenv(key)]


def percent_encode(value: str) -> str:
    return quote(str(value), safe="~-._")


def oauth1_header(method: str, url: str) -> str:
    params = {
        "oauth_consumer_key": os.environ["X_API_KEY"],
        "oauth_nonce": secrets.token_hex(16),
        "oauth_signature_method": "HMAC-SHA1",
        "oauth_timestamp": str(int(time.time())),
        "oauth_token": os.environ["X_ACCESS_TOKEN"],
        "oauth_version": "1.0",
    }
    normalized = "&".join(
        f"{percent_encode(key)}={percent_encode(value)}"
        for key, value in sorted(params.items())
    )
    base_string = "&".join((method.upper(), percent_encode(url), percent_encode(normalized)))
    signing_key = f"{percent_encode(os.environ['X_API_SECRET'])}&{percent_encode(os.environ['X_ACCESS_TOKEN_SECRET'])}"
    signature = base64.b64encode(
        hmac.new(signing_key.encode(), base_string.encode(), hashlib.sha1).digest()
    ).decode()
    params["oauth_signature"] = signature
    return "OAuth " + ", ".join(
        f'{percent_encode(key)}="{percent_encode(value)}"' for key, value in sorted(params.items())
    )


def compose_x_post(title: str, url: str, peak: str) -> str:
    tags = {
        "AI/I": "#AI #Infrastructure",
        "EFM/I": "#Energy #Infrastructure",
        "DS/I": "#Defense #Space",
        "Cross-Peak": "#ThreePeaks",
    }.get(peak, "#RHTC")
    suffix = f"\n\n{peak} · RHTC Policy & Power\n{url}\n{tags}"
    # X shortens every HTTP(S) link to a fixed t.co length. Keeping the local
    # string under 280 as well gives a conservative, predictable payload.
    available = max(20, 280 - len(suffix))
    clean_title = " ".join(title.split())
    if len(clean_title) > available:
        clean_title = clean_title[: max(1, available - 1)].rstrip() + "…"
    return clean_title + suffix


@router.get("/status")
async def x_status() -> dict[str, Any]:
    missing = missing_x_settings()
    return {"configured": not missing, "missing": missing}


@router.post("/publish")
async def publish_to_x(data: XPublishInput) -> dict[str, str]:
    missing = missing_x_settings()
    if missing:
        raise HTTPException(503, "X publishing is not configured. Add " + ", ".join(missing) + " to Railway Variables.")
    if not data.url.lower().startswith(("https://", "http://")):
        raise HTTPException(400, "A valid YouTube video URL is required.")
    hostname = (urlparse(data.url).hostname or "").lower()
    if hostname != "youtube.com" and not hostname.endswith(".youtube.com") and hostname != "youtu.be":
        raise HTTPException(400, "Publish the RHTC YouTube video first. X posts must link to its YouTube URL.")
    text = compose_x_post(data.title, data.url, data.peak)
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(
            CREATE_POST_URL,
            json={"text": text},
            headers={"Authorization": oauth1_header("POST", CREATE_POST_URL)},
        )
    if response.status_code not in (200, 201):
        try:
            payload = response.json()
            message = payload.get("detail") or payload.get("title") or payload.get("errors", [{}])[0].get("message")
        except Exception:
            message = ""
        raise HTTPException(502, "X could not publish the article: " + (str(message) if message else "check the app's write permission and API credits."))
    try:
        post_id = str(response.json()["data"]["id"])
    except (KeyError, TypeError, ValueError) as exc:
        raise HTTPException(502, "X accepted the request but returned no Post ID.") from exc
    return {"post_id": post_id, "url": f"https://x.com/i/web/status/{post_id}", "text": text}
