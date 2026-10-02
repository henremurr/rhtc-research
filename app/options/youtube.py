from __future__ import annotations

import asyncio
import os
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Any

import httpx
from fastapi import APIRouter, File, Form, HTTPException, UploadFile

router = APIRouter(prefix="/api/youtube", tags=["youtube"])
BASE = Path(__file__).parent
ARTWORK_DIR = BASE / "static" / "youtube-artwork"
MAX_AUDIO_BYTES = 100 * 1024 * 1024
UPLOAD_CHUNK_BYTES = 8 * 1024 * 1024

SERIES_ARTWORKS: dict[str, tuple[str, str]] = {
    "ai_infrastructure": ("AI & Infrastructure", "RHTC_AI_and_Infrastructure_16x9.jpg"),
    "energy_fuels_infrastructure": ("Energy, Fuels & Infrastructure", "RHTC_Energy_Fuels_and_Infrastructure_16x9.jpg"),
    "defense_space_infrastructure": ("Defense, Space & Infrastructure", "RHTC_Defense_Space_and_Infrastructure_16x9.jpg"),
    "policy_power_news": ("RHTC Policy & Power", "RHTC_Policy_and_Power_News_16x9.jpg"),
    "think_tank_watch": ("Think-Tank Watch", "RHTC_Think_Tank_Watch_16x9.jpg"),
    "three_peaks_audio_brief": ("Three Peaks Audio Brief", "RHTC_Three_Peaks_Audio_Brief_16x9.jpg"),
    "pentagon_contract_watch": ("Pentagon Contract Watch", "RHTC_Pentagon_Contract_Watch_16x9.jpg"),
}


def missing_youtube_settings() -> list[str]:
    return [
        key
        for key in ("YOUTUBE_CLIENT_ID", "YOUTUBE_CLIENT_SECRET", "YOUTUBE_REFRESH_TOKEN")
        if not os.getenv(key)
    ]


def artwork_for_series(series: str) -> Path:
    item = SERIES_ARTWORKS.get(series)
    if not item:
        raise HTTPException(400, "Choose a valid RHTC YouTube series.")
    path = ARTWORK_DIR / item[1]
    if not path.is_file():
        raise HTTPException(503, f"The {item[0]} video artwork is missing from this deployment.")
    return path


@router.get("/status")
async def youtube_status() -> dict[str, Any]:
    missing = missing_youtube_settings()
    try:
        import imageio_ffmpeg  # noqa: F401
        ffmpeg_ready = True
    except Exception:
        ffmpeg_ready = False
    return {
        "configured": not missing and ffmpeg_ready,
        "missing": missing,
        "ffmpeg_ready": ffmpeg_ready,
        "privacy_note": "Unverified YouTube API projects may restrict uploads to private viewing.",
    }


async def refresh_access_token(client: httpx.AsyncClient) -> str:
    missing = missing_youtube_settings()
    if missing:
        raise HTTPException(503, "YouTube upload is not configured. Add " + ", ".join(missing) + " to Railway Variables.")
    response = await client.post(
        "https://oauth2.googleapis.com/token",
        data={
            "client_id": os.environ["YOUTUBE_CLIENT_ID"],
            "client_secret": os.environ["YOUTUBE_CLIENT_SECRET"],
            "refresh_token": os.environ["YOUTUBE_REFRESH_TOKEN"],
            "grant_type": "refresh_token",
        },
    )
    if response.status_code != 200:
        raise HTTPException(502, "Google could not refresh the YouTube authorization. Reconnect the channel and update its refresh token.")
    token = response.json().get("access_token")
    if not token:
        raise HTTPException(502, "Google returned no YouTube access token.")
    return str(token)


def render_video(audio_path: Path, artwork_path: Path, output_path: Path) -> None:
    try:
        import imageio_ffmpeg
        ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    except Exception as exc:
        raise HTTPException(503, "MP4 conversion is unavailable. Check the imageio-ffmpeg Railway dependency.") from exc
    command = [
        ffmpeg, "-hide_banner", "-loglevel", "error", "-y",
        "-loop", "1", "-framerate", "1", "-i", str(artwork_path),
        "-i", str(audio_path),
        "-vf", "scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2,format=yuv420p",
        "-c:v", "libx264", "-preset", "veryfast", "-tune", "stillimage", "-crf", "29",
        "-r", "30", "-c:a", "aac", "-b:a", "128k", "-shortest", "-movflags", "+faststart",
        str(output_path),
    ]
    try:
        completed = subprocess.run(command, capture_output=True, text=True, timeout=900, check=False)
    except subprocess.TimeoutExpired as exc:
        raise HTTPException(504, "MP4 conversion took too long. Try a shorter episode.") from exc
    if completed.returncode != 0 or not output_path.is_file() or output_path.stat().st_size == 0:
        detail = completed.stderr[-1200:].strip() or "FFmpeg could not encode the supplied MP3."
        raise HTTPException(422, f"MP4 conversion failed: {detail}")


async def start_youtube_upload(client: httpx.AsyncClient, token: str, video_path: Path, title: str, description: str, series_name: str, privacy_status: str) -> dict[str, Any]:
    size = video_path.stat().st_size
    metadata = {
        "snippet": {
            "title": title,
            "description": description,
            "categoryId": "25",
            "tags": ["RHTC", "Three Peaks", series_name],
            "defaultLanguage": "en",
        },
        "status": {
            "privacyStatus": privacy_status,
            "selfDeclaredMadeForKids": False,
        },
    }
    session = await client.post(
        "https://www.googleapis.com/upload/youtube/v3/videos",
        params={"uploadType": "resumable", "part": "snippet,status"},
        json=metadata,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json; charset=UTF-8",
            "X-Upload-Content-Type": "video/mp4",
            "X-Upload-Content-Length": str(size),
        },
    )
    if session.status_code not in (200, 201):
        try:
            message = session.json().get("error", {}).get("message", "")
        except Exception:
            message = ""
        raise HTTPException(502, f"YouTube could not start the upload: {message or 'check the Google API project and channel authorization.'}")
    upload_url = session.headers.get("location")
    if not upload_url:
        raise HTTPException(502, "YouTube did not return an upload session.")
    video_id = None
    with video_path.open("rb") as video:
        offset = 0
        while offset < size:
            chunk = video.read(UPLOAD_CHUNK_BYTES)
            if not chunk:
                break
            end = offset + len(chunk) - 1
            response = await client.put(
                upload_url,
                content=chunk,
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "video/mp4",
                    "Content-Length": str(len(chunk)),
                    "Content-Range": f"bytes {offset}-{end}/{size}",
                },
            )
            if response.status_code == 308:
                accepted = response.headers.get("range", "")
                if accepted:
                    match = re.fullmatch(r"bytes=0-(\d+)", accepted)
                    if not match:
                        raise HTTPException(502, "YouTube returned an invalid resumable-upload range.")
                    confirmed_offset = int(match.group(1)) + 1
                    if confirmed_offset > end + 1:
                        raise HTTPException(502, "YouTube acknowledged bytes beyond the current upload chunk.")
                else:
                    confirmed_offset = 0
                video.seek(confirmed_offset)
                offset = confirmed_offset
                continue
            if response.status_code not in (200, 201):
                try:
                    message = response.json().get("error", {}).get("message", "")
                except Exception:
                    message = ""
                raise HTTPException(502, f"YouTube upload failed: {message or 'the upload did not complete.'}")
            video_id = response.json().get("id")
            break
    if not video_id:
        raise HTTPException(502, "YouTube did not confirm the uploaded video.")
    return {"video_id": str(video_id), "url": f"https://www.youtube.com/watch?v={video_id}", "privacy_status": privacy_status}


@router.post("/publish")
async def publish_video(
    audio: UploadFile = File(...),
    title: str = Form(..., min_length=1, max_length=100),
    description: str = Form("", max_length=5000),
    series: str = Form("policy_power_news"),
    privacy_status: str = Form("private"),
) -> dict[str, Any]:
    if privacy_status not in {"private", "unlisted", "public"}:
        raise HTTPException(400, "Choose Private, Unlisted, or Public visibility.")
    if not title.strip():
        raise HTTPException(400, "Enter a YouTube video title.")
    artwork_path = artwork_for_series(series)
    if missing_youtube_settings():
        raise HTTPException(503, "YouTube upload is not configured. Add YOUTUBE_CLIENT_ID, YOUTUBE_CLIENT_SECRET, and YOUTUBE_REFRESH_TOKEN to Railway Variables.")
    if audio.content_type not in {"audio/mpeg", "audio/mp3", "application/octet-stream"} and not (audio.filename or "").lower().endswith(".mp3"):
        raise HTTPException(415, "Choose the narrated MP3 file.")
    payload = await audio.read(MAX_AUDIO_BYTES + 1)
    if len(payload) > MAX_AUDIO_BYTES:
        raise HTTPException(413, "The MP3 is larger than the 100 MB upload limit.")
    is_mp3 = payload.startswith(b"ID3") or (len(payload) > 1 and payload[0] == 0xFF and payload[1] & 0xE0 == 0xE0)
    if not is_mp3:
        raise HTTPException(400, "The supplied file does not look like a valid MP3.")
    with tempfile.TemporaryDirectory(prefix="rhtc-youtube-") as temp_dir:
        work = Path(temp_dir)
        audio_path = work / "episode.mp3"
        video_path = work / "episode.mp4"
        audio_path.write_bytes(payload)
        await asyncio.to_thread(render_video, audio_path, artwork_path, video_path)
        timeout = httpx.Timeout(connect=20.0, read=180.0, write=180.0, pool=20.0)
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=False) as client:
            token = await refresh_access_token(client)
            result = await start_youtube_upload(client, token, video_path, title.strip(), description.strip(), SERIES_ARTWORKS[series][0], privacy_status)
    return {**result, "title": title.strip(), "series": SERIES_ARTWORKS[series][0]}
