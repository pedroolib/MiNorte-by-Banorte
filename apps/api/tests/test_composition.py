"""Composition Engine sin gastar: executor y diseñador falsos."""

from app import composition as C


def _ex(valores):
    def _run(name, args):
        if name == "get_metric":
            v = valores.get((args["name"], args.get("month")))
            if v is None:
                raise ValueError("sin base")
            return {"value": str(v)}
        if name == "get_signals":
            return {"signals": {"tiene_datos": True, "isr_estimado": "10",
                                "iva_neto": "5", "pct_gasto_deducible": "0.5"}}
        raise ValueError(name)
    return _run


def _insight(kind, sev="info", fam="operations", imp="low", act="low",
             ev="runway_dias"):
    return {"id": kind, "kind": kind, "family": fam, "severity": sev,
            "titulo": f"T {kind}", "detalle": f"D {kind}",
            "financial_impact": imp, "actionability": act,
            "evidencia": [{"señal": ev, "valor": "1", "unidad": "x"}]}


def _design(cards, components):
    return {"cards": [{"insight_id": i["id"], "component": "insight_text",
                       "props": {"title": "t", "body": "b"},
                       "rationale": "test"} for i in cards]}


def test_anchors_con_trend_en_codigo():
    ex = _ex({("ventas", "2026-07"): 100, ("ventas", "2026-06"): 80,
              ("utilidad", "2026-07"): 10, ("utilidad", "2026-06"): 10,
              ("efectivo", "2026-07"): 50, ("efectivo", "2026-06"): None,
              ("isr_estimado", "2026-07"): 5, ("isr_estimado", "2026-06"): 4})
    ancs = C.anchors("2026-07", ex, {"revenue": "c1", "profit": "c2",
                                     "cash": "c3", "estimated_tax": "c4"})
    assert len(ancs) == 4
    rev = ancs[0]
    assert rev["metric"] == "revenue" and rev["value"] == 100.0
    assert rev["trend"] == {"direction": "up", "percentage": 25.0}
    assert rev["analyst_comment"] == "c1"
    assert ancs[1]["trend"] == {"direction": "flat", "percentage": 0.0}
    assert ancs[2]["trend"] is None  # sin previo honesto, no inventado
    assert ancs[3]["trend"]["direction"] == "up"


def test_scoring_y_diversidad():
    a = _insight("a", "warning", "expenses", "high", "high")
    b = _insight("b", "info", "expenses", "low", "low")
    c = _insight("c", "info", "expenses", "low", "low")
    s_a, partes = C.score(a, [])
    assert s_a == 3 + 3 + 2 + 2 + 0 + 0  # sev+impacto+accionable+novedad
    assert partes["repetition_penalty"] == 0
    # 3 de la misma familia -> solo 2 (diversidad)
    eleg = C.discover([a, b, c], [], 3)
    assert [i["kind"] for i in eleg] == ["a", "b"]
    # mostrado la semana pasada -> penalización
    from datetime import datetime, timezone
    exp = [{"insight_kind": "a", "insight_fingerprint": "a|x",
            "shown_at": datetime.now(timezone.utc).isoformat()}]
    s_a2, partes2 = C.score(a, exp)
    assert partes2["novelty"] == 0 and partes2["repetition_penalty"] == -3
    assert s_a2 < s_a


def test_regla_obligatoria_y_sin_problemas(monkeypatch):
    # alertas reales del seed apagadas: hermeticidad del test
    monkeypatch.setattr(C.D, "reserved_cards", lambda month, ex: [])
    crit = _insight("crit", "critical", "risk", "high", "high")
    pool = [crit] + [_insight(f"i{i}") for i in range(5)]
    out = C.compose("2026-07", pool, {}, [], _ex({}), "2026-W30",
                    design_fn=_design,
                    summary_fn=lambda cards, m: "resumen")
    assert out["week_id"] == "2026-W30"
    assert len(out["anchors"]) == 4
    assert any(c["insight_id"] == "crit"
               for c in out["actions"])  # la crítica entra sí o sí
    assert out["summary"] == "resumen"
    assert len(out["_exposures"]) == len(out["actions"]) + len(out["discovery"])
    # sin problemas: 0 acciones, 5 discovery de 5 familias (pool de 6)
    fams = ["operations", "growth", "risk", "tax", "cash_flow", "expenses"]
    pool2 = [_insight(f"j{i}", fam=f) for i, f in enumerate(fams)]
    out2 = C.compose("2026-07", pool2, {}, [], _ex({}), "2026-W31",
                     design_fn=_design,
                     summary_fn=lambda cards, m: "r")
    assert out2["actions"] == [] and len(out2["discovery"]) == 5


def test_dashboard_sin_db_pide_supabase():
    from fastapi.testclient import TestClient

    import app.main as main

    r = TestClient(main.app).get("/api/dashboard/gen")
    assert r.status_code == 503


def test_tope_tres_acciones_con_reservadas(monkeypatch):
    monkeypatch.setattr(
        C.D, "reserved_cards",
        lambda month, ex: [
            {"insight_id": "r1", "component": "receipts_resolution",
             "props": {"count": 1, "total": "10"}, "rationale": "r"},
            {"insight_id": "r2", "component": "receivables_resolution",
             "props": {"count": 2, "total": "20"}, "rationale": "r"}])
    pool = ([_insight("c1", "critical", "risk", "high", "high"),
             _insight("c2", "critical", "risk", "high", "high")]
            + [_insight(f"w{i}", "warning", "tax", "high", "high")
               for i in range(3)])
    out = C.compose("2026-07", pool, {}, [], _ex({}), "2026-W32",
                    design_fn=_design, summary_fn=lambda c, m: "r")
    assert len(out["actions"]) == 3  # 2 reservadas + 1 diseñada
    assert len(out["actions"]) + len(out["discovery"]) <= 8


def test_critical_bar_sin_db():
    from fastapi.testclient import TestClient

    import app.main as main

    r = TestClient(main.app).get("/api/critical-bar",
                                 params={"month": "2026-08"})
    assert r.status_code == 200
    body = r.json()
    assert body["month"] == "2026-08" and body["pendientes"] == 3
    comps = {c["component"] for c in body["items"]}
    # 2 reservadas accionables + 1 crítica determinista (runway 4<=7 del seed)
    assert comps == {"receipts_resolution", "receivables_resolution",
                     "insight_text"}
    assert "tax_summary" not in comps


def test_drill_chat_scenarios_sin_db_piden_supabase():
    from fastapi.testclient import TestClient

    import app.main as main

    client = TestClient(main.app)
    assert client.get("/api/drill",
                      params={"insight_id": "x"}).status_code == 503
    assert client.get("/api/scenarios").status_code == 503
    assert client.post("/api/scenarios", json={}).status_code == 503


def test_rotacion_dura_no_repite_semana_pasada():
    from datetime import datetime, timezone
    pool = [_insight(f"k{i}", "warning" if i < 7 else "info",
                     fam="operations") for i in range(10)]
    # repartir familias para no chocar con diversidad
    fams = ["operations", "growth", "risk", "tax", "cash_flow",
            "expenses", "receivables", "profitability"]
    for i, it in enumerate(pool):
        it["family"] = fams[i % len(fams)]
    ahora = datetime.now(timezone.utc).isoformat()
    exp = [{"insight_kind": f"k{i}", "insight_fingerprint": f"k{i}|x",
            "shown_at": ahora} for i in range(5)]
    eleg = C.discover(pool, exp, 5)
    assert [i["kind"] for i in eleg] == [f"k{i}" for i in range(5, 10)]


def test_rotacion_por_week_id_no_por_fecha():
    from datetime import datetime, timezone
    pool = [_insight(f"k{i}", "warning", fam="operations") for i in range(10)]
    fams = ["operations", "growth", "risk", "tax", "cash_flow",
            "expenses", "receivables", "profitability"]
    for i, it in enumerate(pool):
        it["family"] = fams[i % len(fams)]
    ahora = datetime.now(timezone.utc).isoformat()
    # 3 "semanas" el MISMO día: solo la anterior inmediata excluye
    exp = ([{"insight_kind": f"k{i}", "insight_fingerprint": "x",
             "shown_at": ahora, "week_id": "2026-W40"} for i in range(5)] +
           [{"insight_kind": f"k{i}", "insight_fingerprint": "x",
             "shown_at": ahora, "week_id": "2026-W41"} for i in range(5, 10)])
    eleg = C.discover(pool, exp, 5, wid="2026-W42")
    assert [i["kind"] for i in eleg] == [f"k{i}" for i in range(5)]
