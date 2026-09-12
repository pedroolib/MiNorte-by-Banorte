from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_ok():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"
    assert r.json()["company_id"] == "company_001"


def test_summary_shape():
    r = client.get("/api/summary")
    assert r.status_code == 200
    body = r.json()
    assert body["company_id"] == "company_001"
    assert float(body["ventas"]) == 482300.0
    assert body["gastos_sin_cfdi_count"] == 4
