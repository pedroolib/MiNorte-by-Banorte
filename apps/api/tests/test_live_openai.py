"""Tests contra la API REAL de OpenAI. Cuestan centavos; corren solo con:

    MINORTE_LIVE=1 pytest apps/api/tests/test_live_openai.py -q

Verifican integración de verdad: wrapper, JSON estricto y el Consultor
usando tools sobre tus datos (Supabase con seed cargado).
"""

import os

import pytest

from app.agents import llm

pytestmark = pytest.mark.skipif(
    os.environ.get("MINORTE_LIVE") != "1",
    reason="solo con MINORTE_LIVE=1 (gasta API real)")


def test_chat_smoke():
    r = llm.chat([{"role": "user", "content": "Responde solo con: OK"}],
                 model="gpt-4o-mini")
    assert "OK" in (r.content or "")


def test_chat_json_schema():
    out = llm.chat_json(
        [{"role": "user", "content": "Dame runways 4 y 59."}],
        {"type": "object",
         "properties": {"dias": {"type": "array", "items": {"type": "integer"}}},
         "required": ["dias"], "additionalProperties": False},
        model="gpt-4o-mini")
    assert out == {"dias": [4, 59]}


def test_consultant_contrato_real():
    from app.agents import consultant
    from app.mcp import tools as T

    out = consultant.ask("¿Puedo contratar a alguien por $20,000 al mes?",
                         executor=T.execute)
    assert "evaluar_gasto" in out["tools_usados"]
    assert len(out["respuesta"]) > 50
    print("\nRESPUESTA:", out["respuesta"][:400])


def test_consultant_credito_real():
    from app.agents import consultant
    from app.mcp import tools as T

    out = consultant.ask("Quiero un crédito de $100,000, ¿cuál me conviene?",
                         executor=T.execute)
    assert any(t in out["tools_usados"] for t in
               ("banorte_compare_loans", "banorte_get_credit_options", "evaluar_gasto"))
    assert len(out["respuesta"]) > 50
    print("\nRESPUESTA:", out["respuesta"][:400])


def test_analyst_real_sobre_seed():
    from app.agents import analyst
    from app.mcp import tools as T

    out = analyst.run("2026-08", executor=T.execute, model="gpt-4o-mini")
    assert 1 <= len(out["insights"]) <= 6
    assert "get_signals" in out["tools_usados"]
    for i in out["insights"]:
        assert i["evidencia"], i["kind"]  # ninguna cifra sin cita
    print("\nINSIGHTS:", [(i["severity"], i["titulo"]) for i in out["insights"]])
