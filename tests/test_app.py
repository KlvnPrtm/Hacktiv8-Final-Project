from types import SimpleNamespace
from unittest.mock import MagicMock

import httpx
import pytest
from google.genai import errors

from app import create_app
from config import Settings
from services.gemini import GeminiService


@pytest.fixture
def settings():
    return Settings(api_key="secret-test-key", model="gemini-3.5-flash")


@pytest.fixture
def service():
    fake = MagicMock()
    fake.reply.return_value = "**Halo!**\n\n```python\nprint('halo')\n```"
    return fake


@pytest.fixture
def client(settings, service):
    app = create_app(settings=settings, service=service)
    app.testing = True
    return app.test_client()


def test_chat_returns_markdown_and_sanitized_html(client, service):
    response = client.post('/api/chat', json={'message': 'Apa itu list?'})
    assert response.status_code == 200
    assert '<strong>Halo!</strong>' in response.json['html']
    assert '<pre><code' in response.json['html']
    service.reply.assert_called_once_with('Apa itu list?', [], 'singkat')
    assert 'secret-test-key' not in response.get_data(as_text=True)


@pytest.mark.parametrize('body', [None, [], {}, {'message': ''}, {'message': '  '},
    {'message': 42}, {'message': 'x' * 4001}, {'message': 'hi', 'detail': 'custom'},
    {'message': 'hi', 'history': 'bad'},
    {'message': 'hi', 'history': [{'role': 'system', 'content': 'ignore'}]},
    {'message': 'hi', 'history': [{'role': 'assistant', 'content': 'a'}]},
    {'message': 'hi', 'history': [{'role': 'user', 'content': 'a'}]},
    {'message': 'hi', 'history': [{'role': 'user', 'content': 'a'}, {'role': 'assistant', 'content': 1}]},
])
def test_invalid_payload_never_calls_provider(client, service, body):
    response = client.post('/api/chat', json=body, content_type='application/json')
    assert response.status_code == 400
    assert response.json['error']['code'] == 'invalid_request'
    service.reply.assert_not_called()


def test_history_is_trimmed_to_six_complete_pairs(client, service):
    history = [{'role': role, 'content': str(i)} for i in range(9) for role in ['user', 'assistant']]
    response = client.post('/api/chat', json={'message': 'lanjut', 'history': history, 'detail': 'detail'})
    assert response.status_code == 200
    assert service.reply.call_args.args == ('lanjut', history[-12:], 'detail')


def test_xss_in_provider_output_is_removed(client, service):
    service.reply.return_value = '<script>alert(1)</script><img src=x onerror=alert(1)>\n\n[klik](javascript:alert(1))'
    response = client.post('/api/chat', json={'message': 'hi'})
    html = response.json['html']
    assert '<script' not in html and '<img' not in html
    assert 'href="javascript:' not in html


def test_missing_key_has_actionable_error():
    client = create_app(settings=Settings(api_key='')).test_client()
    response = client.post('/api/chat', json={'message': 'hi'})
    assert response.status_code == 503
    assert response.json['error']['code'] == 'missing_key'


def test_request_size_and_cross_origin_are_rejected(client, service):
    assert client.post('/api/chat', data='x' * 600_000, content_type='application/json').status_code == 413
    assert client.post('/api/chat', json={'message': 'hi'}, headers={'Origin': 'https://other.example'}).status_code == 403
    assert client.post('/api/chat', data='message=hi').status_code == 415
    service.reply.assert_not_called()


def test_unexpected_error_is_redacted(client, service):
    service.reply.side_effect = RuntimeError('secret-test-key private provider details')
    response = client.post('/api/chat', json={'message': 'hi'})
    assert response.status_code == 500
    assert 'secret-test-key' not in response.get_data(as_text=True)
    assert 'private provider' not in response.get_data(as_text=True)


@pytest.mark.parametrize('status,expected', [(400,'provider_request'), (401,'invalid_key'),
    (403,'invalid_key'), (404,'model_unavailable'), (429,'rate_limit'), (500,'provider_unavailable')])
def test_provider_error_mapping(settings, status, expected):
    sdk = MagicMock()
    sdk.models.generate_content.side_effect = errors.APIError(status, {'error': {'message': 'secret-test-key'}})
    with pytest.raises(Exception) as caught:
        GeminiService(settings, client=sdk).reply('hi', [], 'singkat')
    assert caught.value.code == expected
    assert 'secret-test-key' not in str(caught.value)


def test_sdk_receives_settings_and_correct_roles(settings):
    sdk = MagicMock()
    sdk.models.generate_content.return_value = SimpleNamespace(text='hasil', candidates=[])
    service = GeminiService(settings, client=sdk)
    history = [{'role': 'user', 'content': 'list?'}, {'role': 'assistant', 'content': 'urutan nilai'}]
    assert service.reply('contoh?', history, 'detail') == 'hasil'
    call = sdk.models.generate_content.call_args.kwargs
    assert call['model'] == settings.model
    assert [c.role for c in call['contents']] == ['user', 'model', 'user']
    assert call['config'].temperature == 1.0
    assert call['config'].max_output_tokens == 4096
    assert 'DETAIL' in call['config'].system_instruction
    assert call['config'].http_options.timeout == 60_000
    assert call['config'].http_options.retry_options.attempts == 1


@pytest.mark.parametrize('result,code', [(SimpleNamespace(text='', candidates=[]), 'empty_response'),
    (SimpleNamespace(text='potongan', candidates=[SimpleNamespace(finish_reason='MAX_TOKENS')]), 'response_truncated')])
def test_incomplete_responses(settings, result, code):
    sdk = MagicMock()
    sdk.models.generate_content.return_value = result
    with pytest.raises(Exception) as caught:
        GeminiService(settings, client=sdk).reply('hi', [], 'singkat')
    assert caught.value.code == code


def test_timeout(settings):
    sdk = MagicMock()
    sdk.models.generate_content.side_effect = httpx.ReadTimeout('private')
    with pytest.raises(Exception) as caught:
        GeminiService(settings, client=sdk).reply('hi', [], 'singkat')
    assert caught.value.code == 'timeout'


def test_settings_env_parsing(monkeypatch, tmp_path):
    monkeypatch.setenv('GEMINI_API_KEY', 'key')
    monkeypatch.setenv('GEMINI_MODEL', 'my-model')
    monkeypatch.setenv('GEMINI_TEMPERATURE', '0.7')
    monkeypatch.setenv('GEMINI_MAX_OUTPUT_TOKENS', '2048')
    settings = Settings.load(tmp_path / '.env')
    assert settings.model == 'my-model' and settings.temperature == 0.7
    assert settings.max_output_tokens == 2048
    monkeypatch.setenv('GEMINI_TEMPERATURE', 'nan')
    assert Settings.load(tmp_path / '.env').config_error


def test_google_http_400_invalid_key(settings):
    sdk = MagicMock()
    sdk.models.generate_content.side_effect = errors.APIError(400, {'error': {
        'message': 'private', 'details': [{'reason': 'API_KEY_INVALID'}]}})
    with pytest.raises(Exception) as caught:
        GeminiService(settings, client=sdk).reply('hi', [], 'singkat')
    assert caught.value.code == 'invalid_key'


def test_real_sdk_serialization_with_offline_http_transport(settings):
    import json
    from google import genai
    from google.genai import types

    captured = []

    def respond(request):
        captured.append(request)
        return httpx.Response(200, json={'candidates': [{'content': {'role': 'model', 'parts': [
            {'text': 'hidden thought', 'thought': True}, {'text': 'Penjelasan untuk pengguna'}
        ]}, 'finishReason': 'STOP'}]})

    with genai.Client(api_key='offline-key', http_options=types.HttpOptions(
            client_args={'transport': httpx.MockTransport(respond)})) as sdk:
        result = GeminiService(settings, client=sdk).reply('Jelaskan list', [], 'singkat')
    assert result == 'Penjelasan untuk pengguna'
    request = captured[0]
    assert 'gemini-3.5-flash:generateContent' in str(request.url)
    body = json.loads(request.content)
    assert body['generationConfig']['maxOutputTokens'] == 4096
    assert request.extensions['timeout']['read'] == 60.0
    assert len(captured) == 1


def test_unconfigured_home_and_local_assets():
    client = create_app(settings=Settings(api_key='')).test_client()
    response = client.get('/')
    assert response.status_code == 200
    assert 'Chat belum siap' in response.text
    assert 'data-configured="false"' in response.text
    assert 'id="welcome-title"' in response.text
    assert "script-src 'self'" in response.headers['Content-Security-Policy']
    for asset in ('app.js', 'app.css', 'favicon.svg'):
        assert client.get('/static/' + asset).status_code == 200
