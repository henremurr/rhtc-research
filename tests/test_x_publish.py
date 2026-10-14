import os
import asyncio
from unittest.mock import patch

from app.options.x_publish import compose_x_post, missing_x_settings, oauth1_header
from app.options import x_publish


def test_compose_x_post_stays_within_limit_and_includes_link():
    url = "https://example.com/story"
    text = compose_x_post("A" * 600, url, "AI/I")
    assert len(text) <= 280
    assert url in text
    assert "#AI #Infrastructure" in text
    assert text.startswith("A")


def test_x_settings_and_oauth_header():
    values = {
        "X_API_KEY": "consumer-key",
        "X_API_SECRET": "consumer-secret",
        "X_ACCESS_TOKEN": "access-token",
        "X_ACCESS_TOKEN_SECRET": "access-secret",
    }
    with patch.dict(os.environ, values, clear=False):
        assert missing_x_settings() == []
        header = oauth1_header("POST", "https://api.x.com/2/tweets")
    assert header.startswith("OAuth ")
    assert 'oauth_consumer_key="consumer-key"' in header
    assert 'oauth_signature_method="HMAC-SHA1"' in header
    assert 'oauth_signature="' in header


def test_successful_x_publish_returns_the_created_post_without_repeating_request():
    from unittest.mock import AsyncMock

    requests = []
    saved = AsyncMock()

    class FakeResponse:
        status_code = 201

        def json(self):
            return {"data": {"id": "1900123456789"}}

    class FakeClient:
        def __init__(self, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def post(self, url, **kwargs):
            requests.append((url, kwargs))
            return FakeResponse()

    credentials = {
        "X_API_KEY": "consumer-key",
        "X_API_SECRET": "consumer-secret",
        "X_ACCESS_TOKEN": "access-token",
        "X_ACCESS_TOKEN_SECRET": "access-secret",
    }
    with patch.dict(os.environ, credentials, clear=False):
        with patch.object(x_publish.httpx, "AsyncClient", FakeClient):
            with patch.object(x_publish, "oauth1_header", return_value="OAuth test"):
                with patch.object(x_publish, "mark_news_x_published", new=saved):
                    result = asyncio.run(x_publish.publish_to_x(x_publish.XPublishInput(
                        title="A major contract",
                        url="https://www.youtube.com/watch?v=video123",
                        peak="DS/I",
                        story_url="https://example.com/story",
                    )))

    assert result["post_id"] == "1900123456789"
    assert result["url"] == "https://x.com/i/web/status/1900123456789"
    assert len(requests) == 1
    saved.assert_awaited_once()
    assert saved.await_args.args[0].url == "https://example.com/story"
    assert saved.await_args.args[0].post_id == "1900123456789"
