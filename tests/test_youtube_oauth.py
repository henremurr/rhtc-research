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


def start(client):
    response = client.post('/options/api/youtube/connect', headers={'origin': 'https://testserver'}, follow_redirects=False)
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
