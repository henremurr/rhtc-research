import os
from unittest.mock import patch

from app.options.x_publish import compose_x_post, missing_x_settings, oauth1_header


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
