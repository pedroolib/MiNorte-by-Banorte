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
    # T1: calculado del seed (agosto 2026, sin traspasos internos)
    assert float(body["ventas"]) > 0
    assert float(body["gastos"]) > 0
    assert abs(float(body["ventas"]) - float(body["gastos"]) - float(body["utilidad"])) < 0.01
    assert float(body["efectivo"]) > 0
