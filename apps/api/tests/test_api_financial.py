"""Endpoints financieros T4/T5 (funcionan con tabla o fallback live)."""

from decimal import Decimal

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_alerts_agosto():
    r = client.get("/api/alerts")
    assert r.status_code == 200
    body = r.json()
    assert body["month"] == "2026-08"
    rules = {a["rule"]: a for a in body["items"]}
    assert Decimal(rules["sin_factura"]["total"]) == Decimal("2123.00")
    assert rules["sin_factura"]["severity"] == "warning"
    assert Decimal(rules["cuentas_por_cobrar"]["total"]) == Decimal("76550.00")
    assert rules["sin_factura"]["payload"]["component"] == "receipts_resolution"
    assert rules["cuentas_por_cobrar"]["payload"]["component"] == "receivables_resolution"
    severities = {a["severity"] for a in body["items"]}
    assert severities <= {"info", "warning", "critical"}


def test_receivables_cxc():
    r = client.get("/api/receivables")
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 5
    assert Decimal(body["total_pending"]) == Decimal("76550.00")
    assert all(i["status"] == "open" for i in body["items"])


def test_matches_counts():
    r = client.get("/api/matches?limit=1")
    assert r.status_code == 200
    counts = r.json()["counts"]
    assert counts["unmatched"] == 5  # 4 egresos sin factura + 1 devolución-ingreso sin CFDI
    assert counts["auto"] >= 150     # 146 recibidos + 11 cobros
    assert counts["auto"] + counts["review"] + counts["unmatched"] == sum(counts.values())
    r2 = client.get("/api/matches?status=unmatched&limit=10")
    assert len(r2.json()["items"]) == 5


def test_summary_con_cxc_y_sin_factura():
    body = client.get("/api/summary").json()
    assert Decimal(body["cuentas_por_cobrar"]) == Decimal("76550.00")
    assert body["gastos_sin_cfdi_count"] == 4
    assert Decimal(body["gastos_sin_cfdi_total"]) == Decimal("2123.00")


def test_signals_son_datos_sin_juicio():
    body = client.get("/api/signals").json()
    assert body["month"] == "2026-08"
    s = body["signals"]
    assert s["runway_dias"] == 4
    assert Decimal(s["ratio_fondeo_interno"]) > Decimal("0.9")
    assert "severity" not in s and "titulo" not in s
    assert Decimal(s["gasto_por_categoria"]["spei_enviado"]) > 0


def test_metric_ok_y_desconocida():
    r = client.get("/api/metric", params={"name": "runway_dias", "month": "2026-08"})
    assert r.status_code == 200
    assert r.json()["value"] == 4
    r = client.get("/api/metric", params={"name": "no_existe"})
    assert r.status_code == 400
    assert "Disponibles" in r.json()["detail"]
