"""Consultor T8 sin gastar: llm y executor falsos, lógica real."""

import pytest
from fastapi.testclient import TestClient

import app.main as main
from app.agents import consultant


class FakeLLM:
    def __init__(self, respuesta="listo", audit=None):
        self.respuesta = respuesta
        self.audit = audit or []
        self.visto = None

    def run_tool_loop(self, system, history, tools, executor, model=None,
                      max_steps=8, **kwargs):
        self.visto = {"n_tools": len(tools), "history": history, "model": model,
                      "temperature": kwargs.get("temperature")}
        return self.respuesta, self.audit, False


def test_ask_pasa_historial_y_tools(monkeypatch):
    fake = FakeLLM("ok", [{"tool": "evaluar_gasto"}])
    import app.agents.consultant as C
    monkeypatch.setattr(C.llm, "run_tool_loop", fake.run_tool_loop)
    monkeypatch.setattr(C, "_tarjetas", lambda *a, **k: [{"t": 1}])
    out = C.ask("¿contrato?", [{"role": "user", "content": "hola"}],
                executor=lambda n, a: {}, model="m")
    assert out["respuesta"] == "ok"
    assert out["tools_usados"] == ["evaluar_gasto"]
    assert out["truncado"] is False
    assert out["tarjetas"] == [{"t": 1}]
    assert fake.visto["history"][-1] == {"role": "user", "content": "¿contrato?"}
    assert fake.visto["n_tools"] == len(consultant.CONSULTANT_TOOLS)
    assert fake.visto["temperature"] == 0.2  # factual, no creativo
    assert "evaluar_gasto" in consultant.CONSULTANT_TOOLS
    assert "get_variables_gasto" in consultant.CONSULTANT_TOOLS
    assert "simulate_hiring" not in consultant.CONSULTANT_TOOLS
    assert "simulate_loan" not in consultant.CONSULTANT_TOOLS
    assert "send_payment_reminder_email" not in consultant.CONSULTANT_TOOLS


def test_chat_rechaza_vacio():
    assert TestClient(main.app).post("/api/chat", json={"mensaje": "  "}).status_code == 400


def test_loans_preview_sin_confirm(monkeypatch):
    r = TestClient(main.app).post("/api/loans/apply", json={
        "option_id": "cred_simple_negocios", "amount": "100000", "months": 12})
    assert r.status_code == 400
    terms = r.json()["detail"]["terms"]
    assert terms["mock"] is True and float(terms["pago_mensual"]) > 0


def test_loans_registra_con_confirm(monkeypatch):
    guardado = {}
    monkeypatch.setattr(main, "_sb_or_503", lambda: object())
    monkeypatch.setattr(
        "app.repositories.chat_repo.registrar_solicitud",
        lambda sb, cid, terms: {"folio": "SOL-X",
                               "status": "solicitada_mock", **terms})
    r = TestClient(main.app).post("/api/loans/apply", json={
        "option_id": "cred_simple_negocios", "amount": "100000",
        "months": 12, "confirm": True}).json()
    assert r["folio"] == "SOL-X" and r["status"] == "solicitada_mock"


def test_loans_valida(monkeypatch):
    c = TestClient(main.app)
    assert c.post("/api/loans/apply", json={"option_id": "nope", "amount": "1"}).status_code == 400
    assert c.post("/api/loans/apply", json={
        "option_id": "cred_simple_negocios", "amount": "1"}).status_code == 400
    r = c.post("/api/loans/apply", json={
        "option_id": "cred_simple_negocios", "amount": "100000", "months": 99})
    assert r.status_code == 400


def test_contexto_temporal_explicito():
    from app.agents.consultant import _contexto
    ctx = _contexto()
    assert "2026-08" in ctx  # último mes con datos
    assert "month='YYYY-MM'" in ctx
    assert "PROHIBIDO inventar" in ctx


def test_system_prohibe_alucinaciones_vistas():
    import app.agents.consultant as C
    assert "cxc_pct_vencida" in C.SYSTEM
    assert "JAMÁS calcules ni inventes cifras" in C.SYSTEM
    assert "PROHIBIDO inventar" in C._perfil_block({"giro": "X"})


def test_ask_devuelve_llamadas_con_args(monkeypatch):
    import app.agents.consultant as C

    class F:
        def run_tool_loop(self, system, history, tools, executor, model=None,
                          max_steps=8, **k):
            return "ok", [{"tool": "get_merchants",
                           "args": {"rubro": "proveedores_materiales"}}], False

    monkeypatch.setattr(C.llm, "run_tool_loop", F().run_tool_loop)
    monkeypatch.setattr(C, "_tarjetas", lambda *a, **k: [])
    out = C.ask("hola")
    assert out["llamadas"] == [{"tool": "get_merchants",
                                "args": {"rubro": "proveedores_materiales"}}]


def test_tarjetas_sin_tools_es_vacio():
    import app.agents.consultant as C
    assert C._tarjetas("hola", "hola", False, lambda n, a: {}) == []


def test_tarjetas_fallo_diseno_es_vacio(monkeypatch):
    import app.agents.consultant as C
    from app.agents import designer as D
    def _boom(cards, components, executor=None, model=None):
        raise ValueError("mal")
    monkeypatch.setattr(D, "design", _boom)
    assert C._tarjetas("q", "r", True, lambda n, a: {}) == []


def test_tarjetas_cantidad_libre(monkeypatch):
    import app.agents.consultant as C
    from app.agents import designer as D
    visto = {}
    def _ok(cards, components, executor=None, model=None, brief="", exact=True, partial=False, extra_check=None, max_text=2):
        visto["n"] = len(cards)
        visto["exact"] = exact
        visto["brief"] = brief
        assert "tax_summary" not in components  # reservadas fuera
        return {"cards": [{"insight_id": "consulta", "component": "x"},
                          {"insight_id": "consulta-rel", "component": "y"}]}
    monkeypatch.setattr(D, "design", _ok)
    out = C._tarjetas("cuánto debo", "debes 5", True, lambda n, a: {})
    assert len(out) == 2 and visto["n"] == 1  # 1 insight, N tarjetas
    assert visto["exact"] is False and "al menos 1 tarjeta" in visto["brief"]


def test_validar_cifras_verbatim():
    import app.agents.consultant as C
    res = [{"tool": "get_open_receivables",
            "resultado": {"items": [{"amount_pending": "19500.00"}],
                          "total": "98500.00"}}]
    ok = {"insight_id": "q", "component": "hero_number",
          "props": {"label": "L", "sublabel": "S", "value": "98500.00"},
          "rationale": "x"}
    assert C.validar_cifras(ok, res) == []
    mal = {"insight_id": "q", "component": "hero_number",
           "props": {"label": "L", "sublabel": "S", "value": "99,000 MXN"},
           "rationale": "x"}
    errs = C.validar_cifras(mal, res)
    assert any("99,000" in e for e in errs)
    # footnote también se revisa
    fn = {"insight_id": "q", "component": "insight_text",
          "props": {"title": "T", "body": "B sin cifras",
                    "footnote": "debes 100000"},
          "rationale": "x"}
    assert any("100000" in e for e in C.validar_cifras(fn, res))


def test_releer_tools_reutiliza_audit(monkeypatch):
    import app.agents.consultant as C
    vistos = []

    def _ex(name, args):
        vistos.append((name, args))
        return {"ok": 1, "monto": "5"}

    out = C._releer_tools([{"tool": "t1", "args": {"a": 1}},
                           {"tool": "t1", "args": {"a": 1}},
                           {"tool": "t2", "args": {}}], _ex)
    assert vistos == [("t1", {"a": 1}), ("t2", {})]  # deduplica
    assert len(out) == 2


def test_tiene_cifra_rechaza_evasion():
    import app.agents.consultant as C
    ok = {"insight_id": "q", "component": "hero_number",
          "props": {"label": "L", "sublabel": "S", "value": "98500.00"},
          "rationale": "x"}
    assert C.tiene_cifra(ok) == []
    evade = {"insight_id": "q", "component": "hero_number",
             "props": {"label": "Consulta", "sublabel": "Falta el valor",
                       "value": "No disponible"},
             "rationale": "x"}
    assert any("No disponible" in e for e in C.tiene_cifra(evade))
    solo_id = {"insight_id": "abc123", "component": "insight_text",
               "props": {"title": "T", "body": "sin números aquí"},
               "rationale": "x"}
    assert C.tiene_cifra(solo_id) != []  # el id no cuenta como cifra


def test_tabla_datos_plana_y_sin_ruido():
    import app.agents.consultant as C
    res = [{"tool": "get_open_receivables",
            "resultado": {"total": "98500.00",
                          "items": [{"uuid": "abc", "customer": "Luis",
                                     "amount_pending": "19500.0"}]}}]
    t, mapa = C.tabla_datos(res)
    assert "get_open_receivables.total = 98500.00" in t
    assert "amount_pending = 19500.0" in t
    assert "abc" not in t and "uuid" not in t
    assert mapa["get_open_receivables.total"] == "98500.00"


def test_resolver_citas_sustituye_y_rechaza():
    import app.agents.consultant as C
    mapa = {"get_open_receivables.total": "98500.00"}
    c = {"insight_id": "q", "component": "hero_number",
         "props": {"label": "L", "sublabel": "S",
                   "value": "=get_open_receivables.total"},
         "rationale": "x"}
    assert C.resolver_citas(c, mapa) == []
    assert c["props"]["value"] == "98500.00"
    c2 = {"insight_id": "q", "component": "hero_number",
          "props": {"label": "L", "sublabel": "S", "value": "=no_existe"},
          "rationale": "x"}
    assert any("no_existe" in e for e in C.resolver_citas(c2, mapa))


def test_consulta_max_una_texto(monkeypatch):
    import app.agents.consultant as C
    from app.agents import designer as D
    visto = {}

    def _ok(cards, components, executor=None, model=None, brief="",
            exact=True, partial=False, extra_check=None, max_text=2):
        visto["max_text"] = max_text
        return {"cards": []}

    monkeypatch.setattr(D, "design", _ok)
    assert C._tarjetas("q", "r", True, lambda n, a: {}, []) == []
    assert visto["max_text"] == 1  # consulta: visual primero


def test_cifras_texto_solo_montos():
    import app.agents.consultant as C
    res = [{"tool": "t", "resultado": {"total": "98500.00"}}]
    assert C.cifras_texto("Total $98,500.00 por cobrar", res) == []
    assert C.cifras_texto("Total $100,000.00 por cobrar", res) != []
    # años, folios y conteos no dan falsos positivos
    assert C.cifras_texto("Emitida en 2026, folio PILOTO-0017, 5 facturas", res) == []


def test_corregir_cifras_reescribe(monkeypatch):
    import app.agents.consultant as C

    class FakeChat:
        def __init__(self):
            self.visto = None

        def chat(self, messages, model=None, **k):
            self.visto = messages[0]["content"]
            from app.agents.llm import ChatResult
            return ChatResult("Total $98,500.00", [])

    fake = FakeChat()
    import app.agents.llm as L
    monkeypatch.setattr(L, "chat", fake.chat)
    res = [{"tool": "t", "resultado": {"total": "98500.00"}}]
    out = C._corregir_cifras("cuánto", "Total $100,000.00", res, "m")
    assert out == "Total $98,500.00"
    # candidato único -> determinista, sin gastar LLM
    assert fake.visto is None
    # ambiguo (2 candidatos cerca) -> reescritura con lista válida
    res2 = [{"tool": "t", "resultado": {"a": "99000.00", "b": "98500.00"}}]
    out2 = C._corregir_cifras("cuánto", "Total $100,000.00", res2, "m")
    assert out2 == "Total $98,500.00"
    assert "100,000" in fake.visto and "98500.0" in fake.visto
    # sin errores no gasta llamada
    out2 = C._corregir_cifras("cuánto", "Total $98,500.00", res, "m")
    assert out2 == "Total $98,500.00"


def test_correccion_determinista_sin_llm():
    import app.agents.consultant as C
    res = [{"tool": "t", "resultado": {"total": "98500.00"}}]
    out = C._corregir_cifras("cuánto", "Total $99,000.00", res, "m")
    assert out == "Total $98,500.00"  # sin gastar LLM
    assert C._formatear_como(98500.0, "99,000.00") == "98,500.00"
