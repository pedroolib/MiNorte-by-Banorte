"""MCP T8: registry estricto, impls y servidor (sin gastar en LLM)."""

import asyncio

import pytest

from app.mcp import tools as T

ESPERADAS = {
    "banorte_get_transactions", "banorte_get_balance",
    "banorte_get_credit_options", "banorte_compare_loans",
    "sat_list_cfdis", "sat_get_cfdi",
    "get_financial_summary", "get_cash_flow", "get_signals",
    "get_open_receivables", "simulate_hiring", "simulate_loan",
    "get_customer_contact", "prepare_payment_reminder",
    "get_merchants", "get_merchant_detail",
}


def test_registry_completo_y_estricto():
    assert {t["name"] for t in T.TOOLS} == ESPERADAS
    for t in T.TOOLS:
        p = t["parameters"]
        assert p["type"] == "object" and p.get("additionalProperties") is False
        assert set(p["required"]) >= set(p["properties"].keys()), t["name"]
    defs = T.as_tool_defs()
    assert {d.name for d in defs} == ESPERADAS


def test_execute_dispatch_y_error():
    assert T.execute("banorte_get_balance", {})["saldo"] == "1294.68"
    with pytest.raises(ValueError, match="inexistente"):
        T.execute("no_existe", {})


def test_impls_formas():
    txns = T.execute("banorte_get_transactions", {"month": "2026-08", "limit": 5})
    assert len(txns) == 5 and set(txns[0]) >= {"id", "monto", "categoria"}
    with pytest.raises(ValueError, match="no existe"):
        T.execute("sat_get_cfdi", {"uuid": "00000000-0000-4000-8000-000000000000"})
    recs = T.execute("get_open_receivables", {})
    assert len(recs) == 5 and all("folio" in r for r in recs)
    # con utilidad operativa real (negativa en esta cuenta pagadora),
    # 400k NO es viable: el motor lo dice honesto con ranking completo
    comp = T.execute("banorte_compare_loans", {"amount": "400000"})
    assert comp["opciones_evaluadas"] > 0
    assert comp["recomendada"] is None
    assert all(f["veredicto"] != "viable" for f in comp["ranking"])
    chico = T.execute("banorte_compare_loans", {"amount": "30000"})
    assert chico["opciones_evaluadas"] > 0  # estructura válida aunque no viable
    assert T.execute("banorte_get_credit_options", {})["source"] == "mock_banorte"
    sig = T.execute("get_signals", {"month": "2026-08"})
    assert sig["signals"]["runway_dias"] == 4


def test_server_expone_tools():
    import app.mcp.server as S

    assert S.mcp is not None
    tools = asyncio.run(S.mcp.list_tools())
    assert {t.name for t in tools} == ESPERADAS


def test_drill_merchants():
    from app.mcp import tools as T
    prov = T.execute("get_merchants", {"rubro": "proveedores_materiales", "limit": 200})
    assert len(prov) > 10
    assert prov == sorted(prov, key=lambda r: (-float(r["total"]), r["nombre"]))
    assert prov[0]["nombre"] == "LUCIA FERNANDEZ"
    chicos = T.execute("get_merchants", {"min_total": "20000", "limit": 200})
    assert all(float(r["total"]) >= 20000 for r in chicos)
    assert len(chicos) < len(T.execute("get_merchants", {"limit": 200}))
    det = T.execute("get_merchant_detail", {"nombre": "LUCIA FERNANDEZ"})
    assert det["recurrente"] is True and det["meses_activo"] >= 3
    assert len(det["serie"]) == 6
    assert sum(float(s["total"]) for s in det["serie"]) == float(det["total_periodo"])
