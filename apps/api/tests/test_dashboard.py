"""Contrato agregado consumido por la portada MiNorte."""

from decimal import Decimal

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_dashboard_uses_financial_engine_data():
    response = client.get("/api/dashboard")
    assert response.status_code == 200
    body = response.json()
    assert body["month"] == "2026-08"
    assert Decimal(str(body["summary"]["efectivo"])) == Decimal("1294.68")
    assert body["signals"]["runway_dias"] == 4
    assert body["receivables"]["total"] == 5
    assert len(body["monthly"]) == 3
    assert len(body["activity"]) == 35
    assert body["categories"]
    assert body["recent_transactions"]
