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
    fake = FakeLLM("ok", [{"tool": "simulate_hiring"}])
    import app.agents.consultant as C
    monkeypatch.setattr(C.llm, "run_tool_loop", fake.run_tool_loop)
    out = C.ask("¿contrato?", [{"role": "user", "content": "hola"}],
                executor=lambda n, a: {}, model="m")
    assert out == {"respuesta": "ok", "tools_usados": ["simulate_hiring"],
                   "truncado": False}
    assert fake.visto["history"][-1] == {"role": "user", "content": "¿contrato?"}
    assert fake.visto["n_tools"] == len(consultant.CONSULTANT_TOOLS)
    assert fake.visto["temperature"] == 0.2  # factual, no creativo
    assert "simulate_hiring" in consultant.CONSULTANT_TOOLS
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
    monkeypatch.setattr("app.repositories.chat_repo.registrar_solicitud",
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
