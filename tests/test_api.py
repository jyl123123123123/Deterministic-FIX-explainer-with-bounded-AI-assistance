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
