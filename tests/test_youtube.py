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
