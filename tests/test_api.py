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