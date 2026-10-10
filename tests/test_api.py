from fastapi.testclient import TestClient

from fix_explainer.api import app


FIX_MESSAGE = "8=FIX.4.4|9=73|35=D|49=CLIENT12|56=BROKER|11=ORDER-1|55=AAPL|54=1|38=100|40=2|44=150.25|10=030|"


client = TestClient(app)


def test_health_endpoint() -> None:
    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_explain_endpoint_returns_deterministic_json_without_gemini() -> None:
    response = client.post("/api/explain", json={"message": FIX_MESSAGE, "mode": "template"})

    assert response.status_code == 200
    result = response.json()
    assert result["mode"] == "template"
    assert result["message"]["message_type"] == "D"
    assert result["message"]["errors"] == []
    assert result["explanation"]["fallback_used"] is False
    assert "Field" in result["explanation"]["provider_summary"]


def test_explain_endpoint_rejects_non_ascii_input() -> None:
    response = client.post("/api/explain", json={"message": "35=D|55=苹果|"})

    assert response.status_code == 400

def test_explain_contract_matches_browser_and_preserves_legacy_envelope():
    result = client.post('/api/explain', json={'message': FIX_MESSAGE}).json()
    assert result['provider'] == 'template'
    assert result['deterministic'] == result['explanation']['deterministic']
    assert result['provider_summary'] == result['explanation']['provider_summary']


def test_ai_off_never_calls_transport(monkeypatch):
    import fix_explainer.api as api
    monkeypatch.setattr(api.summary_service, 'enabled', False)
    def forbidden(*args, **kwargs):
        raise AssertionError('A disabled provider must not be constructed')
    monkeypatch.setattr(api, 'GeminiExplanationProvider', forbidden)
    result = client.post('/api/explain', json={'message': FIX_MESSAGE, 'mode': 'ai'}).json()
    assert result['provider'] == 'template'
    assert result['fallback_used'] is True


def test_api_stream_controls_and_new_run_reset():
    import time
    with TestClient(app) as connected:
        first = connected.post('/api/trading/start?count=1000&rate=100').json()
        run_id = first['run_id']
        time.sleep(0.12)
        assert connected.post('/api/trading/start').status_code == 409
        paused = connected.post(f'/api/trading/runs/{run_id}/pause?rate=50').json()
        assert paused['status'] == 'PAUSED'
        assert paused['rate'] == 50
        time.sleep(0.08)
        assert connected.get(f'/api/trading/runs/{run_id}').json()['processed'] == paused['processed']
        assert connected.get('/api/analytics/snapshot').json()['total_orders'] > 0
        assert connected.post(f'/api/trading/runs/{run_id}/stop').json()['status'] == 'STOPPED'
        second = connected.post('/api/trading/start?count=1000&rate=100').json()
        assert second['run_id'] != run_id
        time.sleep(0.08)
        fresh = connected.get('/api/analytics/snapshot').json()
        assert fresh['total_orders'] > 0
        assert 'CORRELATION_REJECTED' not in fresh['findings']
        assert connected.post(f"/api/trading/runs/{second['run_id']}/pause").status_code == 200
        assert connected.post(f"/api/trading/runs/{second['run_id']}/resume").json()['status'] == 'RUNNING'
        connected.post(f"/api/trading/runs/{second['run_id']}/stop")


def test_chat_endpoint_returns_backend_reply(monkeypatch):
    import fix_explainer.api as api

    monkeypatch.setenv('FIX_ENABLE_AI', '1')
    monkeypatch.setenv('GEMINI_API_KEY', 'test-key')
    monkeypatch.setenv('GEMINI_MODEL', 'gemini-flash-latest')
    monkeypatch.setattr(api.chat_limiter, 'calls', 0)
    monkeypatch.setattr(api.chat_limiter, 'last_call', None)

    def fake_transport(model, key, payload, timeout):
        assert model == 'gemini-flash-latest'
        assert payload['systemInstruction']['parts'][0]['text']
        assert payload['contents'] == [
            {'role': 'user', 'parts': [{'text': 'Hello'}]},
            {'role': 'model', 'parts': [{'text': 'Hi!'}]},
            {'role': 'user', 'parts': [{'text': 'What is FIX?'}]},
        ]
        return 'Mock Gemini reply.'

    monkeypatch.setattr(api, 'gemini_transport', fake_transport)
    response = client.post('/api/chat', json={'messages': [
        {'role': 'user', 'text': 'Hello'},
        {'role': 'model', 'text': 'Hi!'},
        {'role': 'user', 'text': 'What is FIX?'},
    ]})

    assert response.status_code == 200
    assert response.json() == {'reply': 'Mock Gemini reply.', 'provider': 'gemini'}


def test_chat_endpoint_requires_ai_enabled(monkeypatch):
    monkeypatch.setenv('FIX_ENABLE_AI', '0')
    response = client.post('/api/chat', json={'messages': [{'role': 'user', 'text': 'Hello'}]})

    assert response.status_code == 503
    assert 'not enabled' in response.json()['detail']


def test_chat_endpoint_enforces_request_limits(monkeypatch):
    monkeypatch.setenv('FIX_ENABLE_AI', '1')
    monkeypatch.setenv('GEMINI_API_KEY', 'test-key')
    monkeypatch.setenv('GEMINI_MODEL', 'gemini-flash-latest')

    too_many = [{'role': 'user', 'text': 'hi'}] * 41
    assert client.post('/api/chat', json={'messages': too_many}).status_code == 422

    too_long = [{'role': 'user', 'text': 'x' * 4001}]
    assert client.post('/api/chat', json={'messages': too_long}).status_code == 422

    big_total = [
        {'role': 'user' if i % 2 == 0 else 'model', 'text': 'x' * 4000}
        for i in range(17)
    ]
    response = client.post('/api/chat', json={'messages': big_total})
    assert response.status_code == 400
