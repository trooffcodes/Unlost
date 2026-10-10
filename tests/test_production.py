import io
import json
import os
import subprocess
import sys
import zipfile
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import Mock

import pytest
import requests
from PIL import Image
from redis.exceptions import ConnectionError
from config import Config
from services import ai, pipeline, vector_store
from services.token_manager import user_token_manager
from utils.validation import validate_upload

HEADERS = {'X-Unlost-Request': '1'}


def upload(client, data=b'Invoice for software services, October 2026.', name='invoice.txt'):
    return client.post('/upload', data={'files': (io.BytesIO(data), name)}, headers=HEADERS)


def stub_ai(monkeypatch):
    monkeypatch.setattr(pipeline, 'extract_semantic_metadata', lambda *args: {'suggested_folder': 'Invoices', 'summary': 'Software invoice', 'tags': ['invoice']})
    monkeypatch.setattr(pipeline, 'generate_embedding', lambda text: [1.0, 0.0])
    monkeypatch.setattr('routes.api.generate_embedding', lambda text: [1.0, 0.0])


@pytest.mark.parametrize('persistent', [False, True])
def test_upload_search_isolation_and_clear(client, monkeypatch, request, persistent):
    if persistent:
        request.getfixturevalue('redis_db')
    stub_ai(monkeypatch)
    result = upload(client)
    assert result.status_code == 200
    job = result.json['batch_id']
    assert client.get(f'/status/{job}').json['data']['files'] == {'invoice.txt': 'DONE'}
    assert len(client.get('/files').json['files']) == 1
    assert client.post('/search', json={'query': 'software invoice'}, headers=HEADERS).json['results'][0]['filename'] == 'invoice.txt'
    stranger = client.application.test_client()
    assert stranger.get('/files').json['files'] == []
    assert stranger.get(f'/status/{job}').status_code == 404
    used = client.get('/usage').json['data']['used']
    assert client.post('/clear_data', headers=HEADERS).status_code == 200
    assert client.get('/files').json['files'] == []
    assert client.get('/usage').json['data']['used'] == used


def test_forged_identity_cannot_read_or_delete(client, monkeypatch, tmp_path):
    stub_ai(monkeypatch)
    upload(client)
    with client.session_transaction() as session:
        victim = session['device_id']
    other = client.application.test_client()
    other.set_cookie('device_id', victim)
    assert other.get('/files').json['files'] == []
    other.set_cookie('device_id', '../../outside')
    marker = tmp_path / 'outside'
    marker.write_text('keep')
    assert other.post('/clear_data', headers=HEADERS).status_code == 200
    assert marker.exists()
    assert len(client.get('/files').json['files']) == 1


def test_signed_cookie_tampering(client, monkeypatch):
    stub_ai(monkeypatch)
    upload(client)
    token = client.get_cookie('session').value
    other = client.application.test_client()
    other.set_cookie('session', token + 'tampered')
    assert other.get('/files').json['files'] == []


def test_admin_disabled_and_csrf(client, monkeypatch):
    assert client.get('/dashboard', headers={'Authorization': 'Bearer forged'}).status_code == 401
    assert client.post('/clear_data').status_code == 403
    monkeypatch.setattr(Config, 'ADMIN_PASSWORD', 'test-password')
    assert client.get('/dashboard', auth=('admin', 'wrong')).status_code == 401
    assert client.get('/dashboard', auth=('admin', 'test-password')).status_code == 200
    for payload in [{'device_id': 'a'*32, 'action': 'set_limit', 'limit': -1}, {'device_id': 'a'*32, 'action': []}]:
        assert client.post('/admin/api/user', json=payload, auth=('admin','test-password'), headers=HEADERS).status_code == 400


@pytest.mark.parametrize('payload', [[], None, {'query': []}, {'query': 5}, {'query': 'x'*2001}])
def test_bad_search_json(client, payload):
    assert client.post('/search', data=json.dumps(payload), content_type='application/json', headers=HEADERS).status_code == 400


def test_bad_telemetry_and_feedback(client):
    assert client.post('/telemetry/event', json={'event': []}, headers=HEADERS).status_code == 400
    assert client.post('/feedback', data={'image': (io.BytesIO(b'<svg onload=alert(1)>'), 'evil.svg')}, headers=HEADERS).status_code == 400
    assert client.post('/feedback', data={'message': 'x'*4001}, headers=HEADERS).status_code == 400


def test_upload_limits_and_zip(client, monkeypatch):
    monkeypatch.setattr(Config, 'MAX_FILES_PER_BATCH', 1)
    assert upload(client, b'wrong content', 'fake.pdf').status_code == 400
    assert upload(client, b'', 'empty.txt').status_code == 400
    data = io.BytesIO()
    with zipfile.ZipFile(data, 'w') as archive:
        archive.writestr('one.txt', 'hello')
        archive.writestr('two.txt', 'world')
    assert upload(client, data.getvalue(), 'docs.zip').status_code == 400
    monkeypatch.setattr(Config, 'MAX_FILE_SIZE', 10)
    assert upload(client, b'a'*11).status_code == 413
    client.application.config['MAX_CONTENT_LENGTH'] = 10
    assert upload(client).status_code == 413
    assert client.post('/upload', data=b'a'*20, headers=HEADERS).is_json


def test_archive_path_sanitized(client, monkeypatch):
    stub_ai(monkeypatch)
    data = io.BytesIO()
    with zipfile.ZipFile(data, 'w') as archive:
        archive.writestr('../../<evil>.txt', 'A useful example document with text.')
    response = upload(client, data.getvalue(), 'docs.zip')
    assert response.status_code == 200
    assert client.get('/files').json['files'][0]['filename'] == 'evil.txt'


def test_storage_failure_never_reports_done(client, monkeypatch, redis_db):
    stub_ai(monkeypatch)
    monkeypatch.setattr(vector_store, 'update_record', Mock(side_effect=ConnectionError('offline')))
    response = upload(client)
    job = client.get('/status/' + response.json['batch_id']).json['data']
    assert job['files']['invoice.txt'].startswith('ERROR')
    assert not Config.DB_PATH.exists()


def test_concurrent_storage_and_quota(redis_db):
    def save(i):
        vector_store.add_to_store('user', f'{i}.txt', '', {}, [1, 0])
        return user_token_manager.consume('user', 100)
    with ThreadPoolExecutor(max_workers=4) as pool:
        assert all(pool.map(save, range(20)))
    assert len(vector_store.get_user_files('user')) == 20
    assert user_token_manager.get_usage_stats('user')['used'] == 2000
    user_token_manager.admin_update_user('user', 0, 500)
    with ThreadPoolExecutor(max_workers=4) as pool:
        assert sum(pool.map(lambda _: user_token_manager.consume('user', 100), range(20))) == 5


def test_search_quota_blocks_provider(client, monkeypatch):
    client.get('/')
    with client.session_transaction() as session:
        device = session['device_id']
    user_token_manager.admin_update_user(device, 20000, 20000)
    provider = Mock()
    monkeypatch.setattr('routes.api.generate_embedding', provider)
    assert client.post('/search', json={'query': 'invoice'}, headers=HEADERS).status_code == 403
    provider.assert_not_called()


def test_groq_rotates_keys(monkeypatch):
    monkeypatch.setattr(ai, 'groq_manager', ai.GroqTokenManager(['first', 'second']))
    result = Mock()
    result.json.return_value = {'choices': [{'message': {'content': '{"sufficient":true}'}}]}
    post = Mock(side_effect=[requests.Timeout(), result])
    monkeypatch.setattr(ai.requests, 'post', post)
    assert ai._call_groq('document text', 'test.txt')['sufficient'] is True
    assert post.call_count == 2
    assert post.call_args.kwargs['headers']['Authorization'] == 'Bearer second'


def test_gemini_text_and_image_mime(monkeypatch):
    response = Mock()
    response.json.return_value = {'candidates': [{'content': {'parts': [{'text': '{}'}]}}]}
    post = Mock(return_value=response)
    monkeypatch.setattr(ai.requests, 'post', post)
    ai._call_gemini_vision(b'hello', 'test.txt', 'plain text')
    parts = post.call_args.kwargs['json']['contents'][0]['parts']
    assert parts == [{'text': 'Filename: test.txt\nplain text'}]
    assert 'key=' not in post.call_args.args[0]
    image = io.BytesIO()
    Image.new('RGB', (2, 2)).save(image, 'JPEG')
    ai._call_gemini_vision(image.getvalue(), 'original.png')
    assert post.call_args.kwargs['json']['contents'][0]['parts'][1]['inlineData']['mimeType'] == 'image/jpeg'


def test_vercel_missing_config_fails_closed():
    env = dict(os.environ, VERCEL='1', PYTHONPATH='src')
    for key in ['SECRET_KEY', 'GEMINI_API_KEY', 'REDIS_URL', 'KV_URL']:
        env.pop(key, None)
    result = subprocess.run([sys.executable, '-c', 'import config'], env=env, capture_output=True, text=True)
    assert result.returncode != 0
    assert 'Missing required production configuration' in result.stderr


def test_vercel_entrypoint_limits_and_headers():
    env = dict(os.environ, VERCEL='1', SECRET_KEY='test-only-stable-key-32-characters-long', GEMINI_API_KEY='synthetic', REDIS_URL='redis://localhost:6379')
    result = subprocess.run([sys.executable, '-c', '''
from app import app
client = app.test_client()
response = client.get('/')
assert response.status_code == 200
assert app.config['MAX_CONTENT_LENGTH'] == 4200000
assert 'Secure' in response.headers['Set-Cookie']
assert 'HttpOnly' in response.headers['Set-Cookie']
assert response.headers['Cache-Control'] == 'no-store'
assert client.get('/static/js/app.js').status_code == 200
'''], env=env, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def test_optional_webhook_completes_before_response(client, monkeypatch):
    stub_ai(monkeypatch)
    from utils import webhook
    monkeypatch.setattr(Config, 'WEBHOOK_FILE', 'https://discord.example.invalid/synthetic')
    post = Mock()
    monkeypatch.setattr(webhook.requests, 'post', post)
    assert upload(client).status_code == 200
    post.assert_called_once()
    assert post.call_args.kwargs['timeout'] == 3
    assert post.call_args.kwargs['files']['file'][0] == 'invoice.txt'


def test_error_notification_does_not_forward_sensitive_payload(monkeypatch):
    import logging
    from utils import logger, webhook
    notify = Mock()
    monkeypatch.setattr(webhook, 'notify_error', notify)
    handler = logger.DiscordErrorHandler()
    handler.emit(logging.LogRecord('test', logging.ERROR, 'provider.py', 1, 'secret-token-in-exception', (), None))
    assert 'secret-token' not in notify.call_args.args[0]
    assert 'ERROR' in notify.call_args.args[0]
