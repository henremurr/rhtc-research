from unittest.mock import AsyncMock, patch
from urllib.parse import urlsplit, parse_qs

import httpx
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.options import youtube_oauth as oauth


def client_for(monkeypatch, tmp_path):
    for key in ('ALL_PROXY', 'HTTPS_PROXY', 'HTTP_PROXY', 'all_proxy', 'https_proxy', 'http_proxy'):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv('RHTC_DATA_DIR', str(tmp_path))
    monkeypatch.setenv('YOUTUBE_CLIENT_ID', 'test-client')
    monkeypatch.setenv('YOUTUBE_CLIENT_SECRET', 'test-secret')
    monkeypatch.setenv('YOUTUBE_REDIRECT_URI', 'https://testserver/options/api/youtube/callback')
    app = FastAPI()
    app.include_router(oauth.router)
    parent = FastAPI()
    parent.mount('/options', app)
    return TestClient(parent, base_url='https://testserver')


def start(client, origin='https://testserver'):
    import re
    page = client.get('/options/api/youtube/connect')
    csrf = re.search(r'name="csrf" value="([^"]+)"', page.text).group(1)
    response = client.post('/options/api/youtube/connect', headers={'origin': origin}, data={'csrf': csrf}, follow_redirects=False)
    assert response.status_code == 303
    return parse_qs(urlsplit(response.headers['location']).query)['state'][0]


def test_connect_rejects_foreign_origin(monkeypatch, tmp_path):
    client = client_for(monkeypatch, tmp_path)
    assert client.post('/options/api/youtube/connect', headers={'origin': 'https://evil.example'}).status_code == 403


def test_invalid_state_never_exchanges_code(monkeypatch, tmp_path):
    client = client_for(monkeypatch, tmp_path)
    start(client)
    with patch.object(oauth.httpx.AsyncClient, 'post', new_callable=AsyncMock) as post:
        assert client.get('/options/api/youtube/callback?state=bad&code=secret').status_code == 400
        post.assert_not_called()


def test_callback_saves_encrypted_token_and_prevents_replay(monkeypatch, tmp_path):
    client = client_for(monkeypatch, tmp_path)
    state = start(client)
    result = httpx.Response(200, json={'refresh_token': 'new-token', 'scope': oauth.SCOPE})
    with patch.object(oauth.httpx.AsyncClient, 'post', new_callable=AsyncMock, return_value=result):
        response = client.get('/options/api/youtube/callback', params={'state': state, 'code': 'code'}, follow_redirects=False)
    assert response.status_code == 303
    assert response.headers['location'] == '/options/?youtube=connected'
    assert oauth.saved_refresh_token() == 'new-token'
    with oauth.database() as db:
        encrypted = db.execute('SELECT token FROM youtube_connection').fetchone()[0]
    assert 'new-token' not in encrypted
    assert client.get('/options/api/youtube/callback', params={'state': state, 'code': 'code'}).status_code == 400


def test_denial_keeps_existing_token(monkeypatch, tmp_path):
    client = client_for(monkeypatch, tmp_path)
    monkeypatch.setenv('YOUTUBE_REFRESH_TOKEN', 'existing')
    state = start(client)
    response = client.get('/options/api/youtube/callback', params={'state': state, 'error': 'access_denied'})
    assert 'cancelled' in response.text
    assert oauth.saved_refresh_token() == 'existing'


def test_missing_permission_keeps_existing_token(monkeypatch, tmp_path):
    client = client_for(monkeypatch, tmp_path)
    monkeypatch.setenv('YOUTUBE_REFRESH_TOKEN', 'existing')
    state = start(client)
    result = httpx.Response(200, json={'refresh_token': 'wrong', 'scope': 'openid'})
    with patch.object(oauth.httpx.AsyncClient, 'post', new_callable=AsyncMock, return_value=result):
        response = client.get('/options/api/youtube/callback', params={'state': state, 'code': 'code'})
    assert 'did not grant' in response.text
    assert oauth.saved_refresh_token() == 'existing'


def test_invalid_callback_shows_setup_instead_of_json_error(monkeypatch, tmp_path):
    client = client_for(monkeypatch, tmp_path)
    monkeypatch.setenv('YOUTUBE_REDIRECT_URI', 'wrong')
    response = client.post('/options/api/youtube/connect', headers={'origin': 'https://testserver'})
    assert response.status_code == 200
    assert 'text/html' in response.headers['content-type']
    assert 'Return to dashboard' in response.text
    assert 'https://testserver/options/api/youtube/callback' in response.text
    assert 'disabled' in response.text


def test_railway_domain_supplies_default_callback(monkeypatch, tmp_path):
    client_for(monkeypatch, tmp_path)
    monkeypatch.delenv('YOUTUBE_REDIRECT_URI')
    monkeypatch.setenv('RAILWAY_PUBLIC_DOMAIN', 'example.up.railway.app')
    assert oauth.redirect_uri() == 'https://example.up.railway.app/options/api/youtube/callback'


def test_null_origin_from_private_referrer_policy_is_accepted_with_csrf(monkeypatch, tmp_path):
    client = client_for(monkeypatch, tmp_path)
    assert start(client, origin='null')


def test_null_origin_without_form_token_is_rejected(monkeypatch, tmp_path):
    client = client_for(monkeypatch, tmp_path)
    client.get('/options/api/youtube/connect')
    assert client.post('/options/api/youtube/connect', headers={'origin': 'null'}).status_code == 403


def test_real_dashboard_middleware_accepts_google_callback_without_dashboard_cookie(monkeypatch, tmp_path):
    import re
    from app.options.api import app as dashboard, DASHBOARD_SESSION_COOKIE, dashboard_session_token
    client_for(monkeypatch, tmp_path)
    password = 'test-dashboard-password-long-enough'
    monkeypatch.setenv('RHTC_DASHBOARD_PASSWORD', password)
    parent = FastAPI()
    parent.mount('/options', dashboard)
    client = TestClient(parent, base_url='https://testserver')
    client.cookies.set(DASHBOARD_SESSION_COOKIE, dashboard_session_token(password), path='/options')
    state = start(client)
    client.cookies.delete(DASHBOARD_SESSION_COOKIE, path='/options')
    result = httpx.Response(200, json={'refresh_token': 'callback-token', 'scope': oauth.SCOPE})
    with patch.object(oauth.httpx.AsyncClient, 'post', new_callable=AsyncMock, return_value=result):
        response = client.get('/options/api/youtube/callback', params={'state': state, 'code': 'code'}, follow_redirects=False)
    assert response.status_code == 303
    assert response.headers['location'] == '/options/?youtube=connected'
    assert oauth.saved_refresh_token() == 'callback-token'
    assert client.get('/options/api/youtube/status').status_code == 401
    assert client.get('/options/api/youtube/callback?state=forged&code=code').status_code == 400
