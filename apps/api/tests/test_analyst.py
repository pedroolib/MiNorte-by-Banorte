"""Analista T8 sin gastar: llm falso, lógica y validación reales."""

import pytest
from fastapi.testclient import TestClient

import app.agents.analyst as A
import app.main as main


def _bueno(k, sev="info"):
    return {"kind": k, "severity": sev, "titulo": f"Título {k}",
            "detalle": f"Detalle observado de {k} este mes.",
            "evidencia": [{"señal": "runway_dias", "valor": "4",
                           "unidad": "días"}]}


def _diez():
    sevs = ["critical", "critical"] + ["warning"] * 3 + ["info"] * 5
    return {"insights": [_bueno(f"k{i}", s) for i, s in enumerate(sevs)]}


class FakeLLM:
    def __init__(self, respuestas):
        self.respuestas = list(respuestas)
        self.visto = {}

    def run_tool_loop(self, system, history, tools, executor, model=None,
                      max_steps=8, **kwargs):
        self.visto["tools"] = sorted(t.name for t in tools)
        self.visto["temperature"] = kwargs.get("temperature")
        self.visto["system"] = system
        return "", [{"tool": "get_signals", "args": {"month": "2026-08"}}], False

    def chat_json(self, messages, schema, model=None):
        n = schema["properties"]["insights"]["maxItems"]
        self.visto.setdefault("pedidos", []).append(n)
        self.visto["mensajes"] = [m["content"] for m in messages]
        return self.respuestas.pop(0)


def _fake(monkeypatch, *respuestas):
    import app.agents.analyst as G
    fake = FakeLLM(respuestas)
    monkeypatch.setattr(G.llm, "run_tool_loop", fake.run_tool_loop)
    monkeypatch.setattr(G.llm, "chat_json", fake.chat_json)
    return fake


def _meses(monkeypatch, meses):
    """Parchea el executor por defecto: meses controlados, resto real."""
    import app.agents.analyst as G
    from app.mcp import tools as T
    real = T.execute
    def _ex(name, args):
        if name == "get_months_with_data":
            return {"months": meses, "latest": meses[-1]}
        return real(name, args)
    monkeypatch.setattr(G.T, "execute", _ex)


def test_run_emite_diez_con_evidencia(monkeypatch):
    fake = _fake(monkeypatch, _diez())
    _meses(monkeypatch, ["2026-06", "2026-07", "2026-08"])
    out = A.run("2026-08", company_id="company_001")
    assert len(out["insights"]) == 10
    assert all(i["company_id"] == "company_001" for i in out["insights"])
    assert all(i["evidencia"] for i in out["insights"])
    # valores autoritativos: el modelo dijo "4", el motor manda
    from app.mcp import tools as T
    real = T.get_signals("2026-08")["signals"]
    primero = out["insights"][0]
    assert primero["evidencia"][0]["señal"] == "runway_dias"
    assert primero["evidencia"][0]["valor"] == str(real["runway_dias"])
    assert fake.visto["pedidos"] == [10]  # una sola llamada, sin reintento
    assert fake.visto["temperature"] == 0.2
    assert "2026-08" in fake.visto["system"]


def test_rechaza_senal_inventada_y_comparativo(monkeypatch):
    cat = {"runway_dias"}
    malo_senal = _bueno("x")
    malo_senal["evidencia"] = [{"señal": "ventas[anterior]", "valor": "300000",
                                "unidad": "MXN"}]
    assert "no existe" in A.validar_uno(malo_senal, 3, cat)
    malo_comp = _bueno("y")
    malo_comp["titulo"] = "Ventas estables"
    malo_comp["detalle"] = "Nivel estable comparado con el mes anterior."
    assert "comparativo" in A.validar_uno(malo_comp, 1, cat)
    # con 2+ meses el comparativo sí pasa (hay con qué comparar)
    assert A.validar_uno(malo_comp, 2, cat) is None
    assert A.validar_uno(_bueno("z"), 1, cat) is None


def test_reintento_combinado_pide_solo_faltantes(monkeypatch):
    lote1 = _diez()["insights"]
    lote1[8] = dict(lote1[8], evidencia=[])  # sin evidencia
    malo = _bueno("inventado")
    malo["evidencia"] = [{"señal": "ventas[anterior]", "valor": "1",
                          "unidad": "MXN"}]
    lote1[9] = malo
    lote2 = {"insights": [_bueno("nuevo_a", "warning"),
                          _bueno("nuevo_b", "info")]}
    fake = _fake(monkeypatch, {"insights": lote1}, lote2)
    _meses(monkeypatch, ["2026-06", "2026-07", "2026-08"])
    out = A.run("2026-08", company_id="company_001")
    assert len(out["insights"]) == 10
    assert fake.visto["pedidos"] == [10, 2]  # segundo pide solo 2
    segundo = fake.visto["mensajes"][-1]
    assert "NO los repitas" in segundo and "están mal" in segundo
    kinds = [i["kind"] for i in out["insights"]]
    assert len(set(kinds)) == 10


def test_falla_en_voz_alta_si_persiste(monkeypatch):
    malo = {"insights": [_bueno(f"k{i}") for i in range(10)]}
    for m in malo["insights"]:
        m["evidencia"] = []
    fake = _fake(monkeypatch, malo, malo)
    _meses(monkeypatch, ["2026-08"])
    with pytest.raises(ValueError, match="incompleto tras reintento"):
        A.run("2026-08")
    assert fake.visto["pedidos"] == [10, 10]


def test_para_disenador_alimenta_designer(monkeypatch):
    from app.agents import designer as D

    fake = _fake(monkeypatch, _diez())
    _meses(monkeypatch, ["2026-06", "2026-07", "2026-08"])
    out = A.run("2026-08", company_id="company_001")
    para = A.para_disenador(out["insights"])
    assert len(para) == 10
    assert all(set(p) == {"id", "severity", "titulo", "detalle", "payload"}
               for p in para)
    # el diseñador acepta el shape sin adaptadores
    ok = {"insight_id": para[0]["id"], "component": "hero_number",
          "props": {"label": "L", "sublabel": "S", "value": "4"},
          "rationale": "x"}
    assert D.validate_choice(ok, ["hero_number"]) == []


def test_endpoints_sin_db_piden_supabase():
    client = TestClient(main.app)
    r = client.post("/api/analyst/run", json={"month": "2026-08"})
    assert r.status_code == 503
    r = client.get("/api/analyst/insights", params={"month": "2026-08"})
    assert r.status_code == 503


def test_ordena_por_severidad(monkeypatch):
    from app.agents import analyst as G

    items = [_bueno(f"i{i}", "info") for i in range(5)]
    items += [_bueno(f"w{i}", "warning") for i in range(3)]
    items += [_bueno(f"c{i}", "critical") for i in range(2)]
    fake = _fake(monkeypatch, {"insights": items})
    _meses(monkeypatch, ["2026-06", "2026-07", "2026-08"])
    out = G.run("2026-08")
    sevs = [i["severity"] for i in out["insights"]]
    assert sevs == ["critical"] * 2 + ["warning"] * 3 + ["info"] * 5
    # estable dentro de cada nivel (conserva rankeo del modelo)
    assert [i["kind"] for i in out["insights"][:2]] == ["c0", "c1"]


def test_emision_incluye_catalogo_visible(monkeypatch):
    fake = _fake(monkeypatch, _diez())
    _meses(monkeypatch, ["2026-06", "2026-07", "2026-08"])
    A.run("2026-08")
    emision = fake.visto["mensajes"][-1]
    assert "Catálogo de señales" in emision
    assert "runway_dias" in emision  # nombres exactos en contexto
    assert "metric_catalog" in fake.visto["tools"]  # descubrible vía MCP


def test_rechaza_kind_duplicado(monkeypatch):
    lote = _diez()["insights"]
    lote[9] = dict(lote[0])  # mismo kind que el primero
    fake = _fake(monkeypatch, {"insights": lote},
                 {"insights": [_bueno("nuevo_ok", "info")]})
    _meses(monkeypatch, ["2026-06", "2026-07", "2026-08"])
    out = A.run("2026-08")
    kinds = [i["kind"] for i in out["insights"]]
    assert len(out["insights"]) == 10 and len(set(kinds)) == 10
    assert fake.visto["pedidos"] == [10, 1]


def _exec_meses(meses):
    def _ex(name, args):
        assert name == "get_months_with_data", name
        return {"months": meses, "latest": meses[-1]}
    return _ex


def test_mes_sin_datos_falla_antes_del_llm(monkeypatch):
    fake = _fake(monkeypatch, _diez())
    with pytest.raises(ValueError, match="sin datos"):
        A.run("2026-08", executor=_exec_meses(["2026-07"]))
    assert "pedidos" not in fake.visto  # el LLM nunca fue llamado


def test_rechaza_senal_sin_valor_en_el_mes():
    cat = {"runway_dias", "ventas"}
    items = [_bueno("x")]
    v, f = A._partir(items, "2026-08", "c1", 3, cat,
                     {"runway_dias": None, "ventas": "1"},
                     {"runway_dias": "días", "ventas": "MXN"}, set())
    assert v == [] and "sin valor" in f[0]["motivo"]


def test_analista_sabe_de_reservadas():
    assert "tax_summary" in A.SYSTEM and "receivables_resolution" in A.SYSTEM
    assert "PROHIBIDO un insight que solo repita esos totales" in A.SYSTEM
