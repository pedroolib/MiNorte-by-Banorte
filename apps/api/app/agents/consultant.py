"""Consultor Financiero (spec #3.4): interpreta, nunca calcula.

Responde sobre el negocio usando SOLO tools (números del motor).
El modelo redacta; los montos siempre vienen de tools.
"""

from __future__ import annotations

from app.agents import llm
from app.config import get_settings
from app.mcp import tools as T

SYSTEM = """Eres el consultor financiero de una PyME mexicana, dentro de la app MiNorte by Banorte.
Hablas español simple, sin jerga contable, como un asesor de confianza, no como un ERP.

Reglas duras:
- JAMÁS calcules ni inventes cifras: todo número sale de llamar tools primero.
- Si la pregunta pide simular (contratar, crédito), llama la tool de simulación con los parámetros dichos.
- Cita las cifras exactas que devuelven las tools.
- Si falta un dato, dilo y pide lo mínimo necesario.
- Respuestas cortas (~120 palabras) salvo que pidan detalle.
- Moneda MXN, fechas America/Mexico_City.
- Investigación por niveles (progresiva, como un contador):
  Nivel 0 = signals/brief (totales por rubro con n_negocios y hints).
  Nivel 1 = get_merchants (filtra por rubro/monto, trae 10, 50 o todos).
  Nivel 2 = get_merchant_detail (serie mensual + recurrencia de un comercio).
  Profundiza cuando (a) pregunten un quién/cuál específico, (b) un hint_drill
  lo sugiera, o (c) el top agregado no explique el grueso del rubro.
  Prioriza completitud sobre velocidad: mejor 2 llamadas con el dato que
  una respuesta sin él.
- Lista vacía de un tool = filtros muy estrictos, NO ausencia de datos:
  reintenta sin rubro o con limit mayor antes de decir "no hay".
  Preguntas de cobertura ("de qué meses tienes", "qué hay") se responden
  del rango conocido 2026-06 a 2026-08 sin inventar.
- Anti-alucinación (casos vistos en pruebas):
  crece/decrece SOLO según el signo del número (positivo = crece);
  jamás digas "cero" si el valor es distinto de cero;
  vencida = due_date anterior al fin de mes: usa cxc_pct_vencida tal cual,
  no la recalcules ni la inviertas;
  compara únicamente meses con datos (usa los month de las tools)."""


def _perfil_block(perfil: dict | None) -> str:
    if not perfil:
        return ""
    emp = f", {perfil['empleados']} empleados" if perfil.get("empleados") else ""
    notas = f" Notas del dueño: {perfil['notas']}" if perfil.get("notas") else ""
    return (f"\nContexto del negocio: {perfil.get('giro', '')} "
            f"en {perfil.get('ciudad', '')}, {perfil.get('estado', '')} "
            f"({perfil.get('tamanio', '')}, modelo {perfil.get('modelo', '')}{emp})."
            f"{notas} Adapta vocabulario y focos al giro. PROHIBIDO inventar "
            "benchmarks sectoriales ('el promedio del sector es…'): solo usas "
            "datos de las tools de ESTE negocio.")


def _contexto() -> str:
    """Contexto temporal dinámico: el modelo no sabe qué día es ni qué
    meses tienen datos. Sin esto inventa años y rellena con ceros."""
    from datetime import date as _date

    from app import data as _data

    try:
        ultimo = _data.latest_month()
    except Exception:
        ultimo = "2026-08"
    return (f"\nHoy es {_date.today().isoformat()} (America/Mexico_City). "
            f"Los datos cubren 2026-06 a {ultimo}. "
            "'Este mes' en preguntas del negocio = ÚLTIMO MES CON DATOS "
            f"({ultimo}), NO el mes calendario actual. "
            "Cuando pregunten por un mes ('julio', 'el mes pasado', 'ese mes'), "
            "pasa month='YYYY-MM' explícito en el tool. "
            "Un mes SIN DATOS no es una caída: si el brief dice SIN MOVIMIENTOS, "
            "diló y ofrece el último mes con datos. "
            "PROHIBIDO inventar cifras o rellenar con ceros: si un tool no "
            "devolvió el dato de un mes, llama el tool correcto para ese mes.")

CONSULTANT_TOOLS = [
    "get_financial_summary", "get_cash_flow", "get_signals",
    "get_open_receivables", "simulate_hiring", "simulate_loan",
    "banorte_get_credit_options", "banorte_compare_loans",
    "banorte_get_transactions", "get_merchants", "get_merchant_detail",
]


def tool_defs():
    por_nombre = {t["name"]: t for t in T.TOOLS}
    return [llm.ToolDef(t["name"], t["description"], t["parameters"])
            for t in T.TOOLS if t["name"] in CONSULTANT_TOOLS]


def ask(texto: str, history: list[dict] | None = None,
        executor=None, model: str | None = None,
        perfil: dict | None = None) -> dict:
    """Una pregunta. Devuelve {respuesta, tools_usados, truncado}."""
    s = get_settings()
    respuesta, audit, truncado = llm.run_tool_loop(
        SYSTEM + _contexto() + _perfil_block(perfil),
        (history or []) + [{"role": "user", "content": texto}],
        tool_defs(), executor or T.execute,
        model or s.OPENAI_REASONING_MODEL, temperature=0.2)
    return {"respuesta": respuesta,
            "tools_usados": [a["tool"] for a in audit],
            "llamadas": [{"tool": a["tool"], "args": a.get("args", {})}
                         for a in audit],
            "truncado": truncado}
