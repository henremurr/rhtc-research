from fastapi import HTTPException
import pytest

from app.options.youtube import SERIES_ARTWORKS, artwork_for_series


def test_youtube_series_map_has_seven_unique_artworks():
    filenames = [filename for _, filename in SERIES_ARTWORKS.values()]
    assert len(filenames) == 7
    assert len(set(filenames)) == 7


def test_invalid_youtube_series_is_rejected():
    with pytest.raises(HTTPException) as error:
        artwork_for_series("unknown")
    assert error.value.status_code == 400


def test_set_custom_thumbnail_uploads_rhtc_artwork(tmp_path):
    import asyncio

    from app.options.youtube import set_custom_thumbnail

    artwork = tmp_path / "artwork.jpg"
    artwork.write_bytes(b"rhtc-jpeg")

    class Response:
        status_code = 200

    class Client:
        async def post(self, url, **kwargs):
            self.request = (url, kwargs)
            return Response()

    client = Client()
    assert asyncio.run(set_custom_thumbnail(client, "token", "video123", artwork)) is True
    url, request = client.request
    assert url.endswith("/thumbnails/set")
    assert request["params"] == {"videoId": "video123"}
    assert request["content"] == b"rhtc-jpeg"
    assert request["headers"]["Content-Type"] == "image/jpeg"


def test_set_custom_thumbnail_reports_api_failure(tmp_path):
    import asyncio

    from app.options.youtube import set_custom_thumbnail

    artwork = tmp_path / "artwork.jpg"
    artwork.write_bytes(b"rhtc-jpeg")

    class Response:
        status_code = 403

    class Client:
        async def post(self, url, **kwargs):
            return Response()

    assert asyncio.run(set_custom_thumbnail(Client(), "token", "video123", artwork)) is False


def test_confirmed_news_upload_is_saved_server_side_before_response(tmp_path):
    import asyncio
    import io
    import os
    from unittest.mock import AsyncMock, patch

    from starlette.datastructures import Headers, UploadFile
    from app.options import youtube

    artwork = tmp_path / "artwork.jpg"
    artwork.write_bytes(b"artwork")

    class FakeClient:
        def __init__(self, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

    saved = AsyncMock()
    form_file = UploadFile(
        filename="episode.mp3",
        file=io.BytesIO(b"ID3 test audio"),
        headers=Headers({"content-type": "audio/mpeg"}),
    )

    def fake_render(audio_path, artwork_path, video_path):
        video_path.write_bytes(b"test mp4")

    async def fake_upload(*args, **kwargs):
        return {
            "video_id": "video123",
            "url": "https://www.youtube.com/watch?v=video123",
            "privacy_status": "public",
        }

    with patch.dict(os.environ, {
        "YOUTUBE_CLIENT_ID": "client-id",
        "YOUTUBE_CLIENT_SECRET": "client-secret",
        "YOUTUBE_REFRESH_TOKEN": "refresh-token",
    }):
        with patch.object(youtube, "artwork_for_series", return_value=artwork), \
             patch.object(youtube, "render_video", side_effect=fake_render), \
             patch.object(youtube, "refresh_access_token", new=AsyncMock(return_value="access-token")), \
             patch.object(youtube, "start_youtube_upload", new=AsyncMock(side_effect=fake_upload)), \
             patch.object(youtube, "set_custom_thumbnail", new=AsyncMock(return_value=True)), \
             patch.object(youtube, "mark_news_published", new=saved), \
             patch.object(youtube.httpx, "AsyncClient", FakeClient):
            result = asyncio.run(youtube.publish_video(
                audio=form_file,
                title="RHTC Policy & Power | Test story",
                description="Test description",
                series="policy_power_news",
                privacy_status="public",
                story_url="https://example.com/story",
            ))

    assert result["video_id"] == "video123"
    saved.assert_awaited_once()
    assert saved.await_args.args[0].url == "https://example.com/story"
    assert saved.await_args.args[0].video_id == "video123"
