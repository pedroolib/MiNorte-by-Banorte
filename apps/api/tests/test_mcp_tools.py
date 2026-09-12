"""MCP T8: registry estricto, impls y servidor (sin gastar en LLM)."""

import asyncio

import pytest

from app.mcp import tools as T

ESPERADAS = {
    "banorte_get_transactions", "banorte_get_balance",
    "banorte_get_credit_options", "banorte_compare_loans",
    "sat_list_cfdis", "sat_get_cfdi",
    "get_financial_summary", "get_cash_flow", "get_signals",
    "get_months_with_data", "project_next_month",
    "get_metric", "metric_catalog",
    "get_open_receivables", "get_variables_gasto", "evaluar_gasto",
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
    assert recs["count"] == 5 and len(recs["items"]) == 5
    assert all("folio" in r for r in recs["items"])
    assert recs["total"] == "76550.00"  # total determinista incluido
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


def test_get_metric_y_catalogo():
    from app.mcp import tools as T

    m = T.execute("get_metric", {"name": "runway_dias", "month": "2026-08"})
    assert m["value"] == 4 and m["unidad"] == "días" and m["familia"] == "liquidez"
    cat = T.execute("metric_catalog", {})
    assert len(cat) >= 40 and all(
        set(e) == {"nombre", "descripcion", "unidad", "familia"} for e in cat)
    with pytest.raises(ValueError, match="Disponibles"):
        T.execute("get_metric", {"name": "no_existe", "month": None})


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


def test_evaluar_gasto_registry_y_faltantes():
    from app.mcp import tools as T
    t = next(x for x in T.TOOLS if x["name"] == "evaluar_gasto")
    items = t["parameters"]["properties"]["variables"]["items"]
    assert items["additionalProperties"] is False
    assert items["required"] == ["nombre", "valor", "unidad"]
    assert "simulate_hiring" not in {x["name"] for x in T.TOOLS}
    assert "simulate_loan" not in {x["name"] for x in T.TOOLS}
    import pytest
    with pytest.raises(Exception, match="falta:"):
        T.execute("evaluar_gasto", {"expense_type": "auto", "month": None,
                                    "horizon_months": None, "variables": [],
                                    "etapas": None})
    g = T.execute("get_variables_gasto", {"expense_type": "renta"})
    assert any(v["nombre"] == "monthly_rent" for v in g["variables"])


def test_get_months_with_data():
    from app.mcp import tools as T

    r = T.execute("get_months_with_data", {})
    assert r["months"] == ["2026-06", "2026-07", "2026-08"]
    assert r["latest"] == "2026-08"


def test_project_next_month_tool():
    from app.mcp import tools as T

    p = T.execute("project_next_month", {"month": "2026-08"})
    assert p["month_proyectado"] == "2026-09"
    assert set(p) >= {"ventas", "gastos", "utilidad", "metodo",
                      "confianza", "supuestos", "base_meses"}
