"""Analista Financiero (spec #3.3): interpreta señales, nunca calcula.

Lee signals() + alertas deterministas (vía tools MCP) y emite EXACTAMENTE
10 insights rankeados con evidencia obligatoria. Su salida alimenta al
Diseñador (`para_disenador()` entrega el shape que `design()` consume).

Regla de hierro: NINGÚN dato sale del modelo. Todo número o lista de
meses viene de una tool MCP (executor); lo que el modelo devuelve en
evidencia se SOBRESCRIBE con los valores reales antes de guardar.
El modelo elige QUÉ citar (nombres del catálogo visible); el código
pone los NÚMEROS. Inventar un valor es imposible por construcción.

Guardas deterministas:
- mes fuera de get_months_with_data -> error sin gastar LLM;
- evidencia.señal debe existir en metric_catalog() (mata `ventas[anterior]`);
- señal con valor None (sin base) -> evidencia rechazada;
- kind duplicado -> rechazado (unique company/month/kind);
- con un solo mes con datos, lenguaje comparativo rechazado;
- máximo 1 reintento combinado; si persiste, fallo sin guardar nada.
"""

from __future__ import annotations

import re
import uuid

from app.agents import llm
from app.agents.consultant import _contexto, _perfil_block
from app.config import get_settings
from app.mcp import tools as T

N_INSIGHTS = 10

FAMILIES = ("profitability", "cash_flow", "expenses", "receivables",
            "tax", "growth", "risk", "operations")
IMPACTS = ("high", "medium", "low")

ANCHOR_METRICS = ("revenue", "profit", "cash", "estimated_tax")

COMPARATIVOS = re.compile(
    r"estable|crece|creci[óo]|cae|ca[íi]da|aumenta?|disminuye|"
    r"anterior|previo|comparad|vs\.? |respecto al|frente al|"
    r"mes pasado|se mantiene",
    re.IGNORECASE)

SYSTEM = """Eres el analista financiero de una PyME mexicana, dentro de la app MiNorte by Banorte.
Tu trabajo: convertir señales numéricas en insights rankeados que un diseñador usará para elegir tarjetas.

Reglas duras:
- JAMÁS calcules ni inventes cifras: todo número sale de llamar tools primero (get_signals, metric_catalog, get_metric, get_months_with_data; alertas vía get_financial_summary si hace falta).
- Antes de analizar un mes, verifica get_months_with_data: un mes fuera de esa lista NO tiene datos (no lo analices ni lo compares con nada).
- Emite EXACTAMENTE {n} insights, ordenados por urgencia, con kinds TODOS DISTINTOS. Sin relleno con generalidades: si un ángulo no tiene dato, explora otro ángulo real (otro rubro, concentración, vencidos, caja, merchants).
- Cada insight tiene severidad: critical (requiere acción ya: caja, vencidos), warning (vigilar: caídas, concentración), info (contexto útil).
- Tres tarjetas se generan AUTOMÁTICAMENTE sin ti (no gastes insights en
  repetirlas): tax_summary (ISR estimado, IVA neto, % deducible),
  receipts_resolution (conteo y total de gastos sin factura) y
  receivables_resolution (conteo y total de CxC). Tus insights deben cubrir
  lo que esas tarjetas NO dicen (vencidas, antigüedad, concentración,
  tendencias con base); PROHIBIDO un insight que solo repita esos totales.
- Cada insight declara: family (una de profitability, cash_flow, expenses,
  receivables, tax, growth, risk, operations), financial_impact
  (high/medium/low: cuánto dinero mueve el tema) y actionability
  (high: hay acción concreta ya; medium: vigilar o preparar; low: solo contexto).
- Además escribes anchor_analysis: UN comentario por métrica principal
  (revenue, profit, cash, estimated_tax). Solo interpretación cualitativa
  con lo que viste en tools (nivel, tendencia, causa observable):
  PROHIBIDO inventar cifras en el comentario (los números los pone el
  sistema). Sin comparativos si hay un solo mes con datos.
- Cada insight cita su evidencia con el nombre EXACTO de la señal del catálogo visible abajo (p. ej. {{"señal": "runway_dias"}}). PROHIBIDO inventar
  nombres de señal (`ventas[anterior]`, `ventas_totales`, `current_ratio`, `dso` y similares NO existen). Solo cita señales cuyo valor viste en una tool.
- PROHIBIDO inventar benchmarks sectoriales, proyecciones o causas no observables en los datos. Describe lo que ves, no porqués.
- Comparaciones SOLO entre meses de get_months_with_data. Si hay UN SOLO mes, PROHIBIDO
  lenguaje comparativo (estable, crece, cae, aumenta, disminuye, anterior, previo, vs, respecto al):
  describe el nivel observado, no su tendencia.
- Español simple, títulos de ≤12 palabras, detalle de ≤40 palabras.
- Moneda MXN, fechas America/Mexico_City."""

ANALYST_TOOLS = ["get_signals", "metric_catalog", "get_metric",
                 "get_months_with_data", "get_financial_summary",
                 "get_open_receivables", "get_cash_flow"]


def insight_schema(n: int) -> dict:
    return {
        "type": "object", "additionalProperties": False,
        "properties": {
            "anchor_analysis": {
                "type": "array", "minItems": 4, "maxItems": 4,
                "items": {
                    "type": "object", "additionalProperties": False,
                    "properties": {
                        "metric": {"type": "string",
                                   "enum": ["revenue", "profit", "cash",
                                            "estimated_tax"]},
                        "comment": {"type": "string"},
                    },
                    "required": ["metric", "comment"],
                },
            },
            "insights": {
                "type": "array", "minItems": n, "maxItems": n,
                "items": {
                    "type": "object", "additionalProperties": False,
                    "properties": {
                        "kind": {"type": "string"},
                        "family": {"type": "string",
                                   "enum": list(FAMILIES)},
                        "severity": {"type": "string",
                                     "enum": ["info", "warning", "critical"]},
                        "titulo": {"type": "string"},
                        "detalle": {"type": "string"},
                        "financial_impact": {"type": "string",
                                             "enum": list(IMPACTS)},
                        "actionability": {"type": "string",
                                          "enum": list(IMPACTS)},
                        "evidencia": {
                            "type": "array", "minItems": 1,
                            "items": {
                                "type": "object", "additionalProperties": False,
                                "properties": {
                                    "señal": {"type": "string"},
                                },
                                "required": ["señal"],
                            },
                        },
                    },
                    "required": ["kind", "family", "severity", "titulo",
                                 "detalle", "financial_impact",
                                 "actionability", "evidencia"],
                },
            },
        },
        "required": ["anchor_analysis", "insights"],
    }


# Compatibilidad estricta: el schema de emisión vive en una sola función.
INSIGHT_SCHEMA = insight_schema(N_INSIGHTS)


def tool_defs():
    por_nombre = {t["name"]: t for t in T.TOOLS}
    return [llm.ToolDef(t["name"], t["description"], t["parameters"])
            for t in T.TOOLS if t["name"] in ANALYST_TOOLS]


def validar_uno(i: dict, n_meses: int, catalogo: set[str]) -> str | None:
    """None si válido; motivo si no (para el reintento combinado).

    Valida FORMA y nombres; los VALORES los pone el código después
    (sobrescritura autoritativa), así que aquí no se revisan.
    """
    if i.get("severity") not in ("info", "warning", "critical"):
        return f"severidad inválida: {i.get('severity')!r}"
    if i.get("family") not in FAMILIES:
        return f"familia inválida: {i.get('family')!r}"
    for campo in ("financial_impact", "actionability"):
        if i.get(campo) not in IMPACTS:
            return f"{campo} inválido: {i.get(campo)!r}"
    if not i.get("titulo") or not i.get("detalle"):
        return "título o detalle vacío"
    ev = i.get("evidencia") or []
    if not ev:
        return "sin evidencia"
    for e in ev:
        if not e.get("señal"):
            return f"evidencia sin señal: {e}"
        if e["señal"] not in catalogo:
            return (f"señal '{e['señal']}' no existe en el catálogo "
                    "(nombre inventado)")
    if n_meses < 2 and (COMPARATIVOS.search(i.get("titulo", ""))
                        or COMPARATIVOS.search(i.get("detalle", ""))):
        return ("lenguaje comparativo con un solo mes con datos "
                "(describe el nivel, no la tendencia)")
    return None


def _con_ids(items: list[dict], month: str, company_id: str,
             valores: dict, unidades: dict) -> list[dict]:
    """Asigna id y SOBRESCRIBE valor/unidad de cada evidencia con los
    números reales del motor (vía MCP). Lo que el modelo escribió como
    valor se descarta: el modelo elige qué citar, el código pone cuánto."""
    out = []
    for i in items:
        ev = [{"señal": e["señal"], "valor": str(valores[e["señal"]]),
               "unidad": unidades[e["señal"]]} for e in i["evidencia"]]
        out.append({
            "id": uuid.uuid4().hex[:8], "company_id": company_id,
            "month": month, "kind": i["kind"], "family": i["family"],
            "severity": i["severity"],
            "titulo": i["titulo"], "detalle": i["detalle"],
            "financial_impact": i["financial_impact"],
            "actionability": i["actionability"],
            "evidencia": ev})
    return out


def validar_anchors(items: list[dict]) -> str | None:
    """4 comentarios, una métrica distinta cada uno, sin vacíos."""
    if len(items) != 4:
        return f"anchor_analysis debe tener 4, trae {len(items)}"
    metrics = [a.get("metric") for a in items]
    if set(metrics) != set(ANCHOR_METRICS):
        return f"métricas incompletas: {metrics}"
    for a in items:
        if not (a.get("comment") or "").strip():
            return f"comentario vacío en {a.get('metric')}"
    return None


def para_disenador(guardados: list[dict]) -> list[dict]:
    """Shape que `designer.design()` consume: id + texto + severidad.

    El Diseñador resuelve cifras por nombre vía get_metric; aquí viaja
    lo rankeado + su kind como pista, nunca montos sueltos.
    """
    return [{"id": g["id"], "severity": g["severity"],
             "titulo": g["titulo"], "detalle": g["detalle"],
             "payload": {"kind": g.get("kind"),
                         "evidencia": g.get("evidencia", [])}}
            for g in guardados]


def run(month: str, executor=None, model: str | None = None,
        perfil: dict | None = None, company_id: str = "company_001") -> dict:
    """Un mes. Devuelve {month, insights (10), tools_usados}.

    Todo dato sale de tools MCP vía executor. Mes sin datos -> ValueError
    ANTES de gastar LLM.
    """
    s = get_settings()
    ex = executor or T.execute

    resp_meses = ex("get_months_with_data", {})
    meses = resp_meses.get("months", [])
    if month not in meses:
        raise ValueError(f"mes {month} sin datos; meses con datos: {meses}")

    cat = ex("metric_catalog", {})
    catalogo = {e["nombre"] for e in cat}
    unidades = {e["nombre"]: e["unidad"] for e in cat}
    sig = ex("get_signals", {"month": month})
    valores = sig.get("signals", {})

    system = (SYSTEM.format(n=N_INSIGHTS) + _contexto() + _perfil_block(perfil)
              + f"\nMeses con datos (get_months_with_data): {meses}. "
              f"Mes a analizar: {month}.")
    catalogo_txt = ("Catálogo de señales (nombres exactos a citar):\n" +
                    "\n".join(f"- {e['nombre']}: {e['descripcion']} "
                               f"({e['unidad']})" for e in cat))
    tabla = ("Señales de {mm} (get_signals, valores reales):\n".format(mm=month) +
             "\n".join(f"- {k} = {v}" for k, v in sorted(valores.items())
                       if not isinstance(v, dict)))
    _, audit, truncado = llm.run_tool_loop(
        system,
        [{"role": "user", "content":
          f"Analiza el mes {month} de la empresa {company_id}: verifica "
          "get_months_with_data, llama get_signals (y otros tools si hace "
          "falta) y emite EXACTAMENTE "
          f"{N_INSIGHTS} insights rankeados con su evidencia."}],
        tool_defs(), ex,
        model or llm.tool_model(), temperature=0.2)
    llamadas = [{"tool": a["tool"], "args": a.get("args", {})} for a in audit]
    modelo = model or s.OPENAI_REASONING_MODEL

    out = llm.chat_json(
        [{"role": "system", "content": system},
         {"role": "user", "content":
          f"Con los datos ya consultados para {month}, emite EXACTAMENTE "
          f"{N_INSIGHTS} insights. Herramientas usadas: {llamadas}.\n"
          f"{catalogo_txt}\n{tabla}\n"
          "En evidencia cita SOLO {señal} con nombres de esa lista "
          "(sin valor: los números los pone el sistema). Si te falta un "
          "dato, explora otro ángulo real en vez de inventarlo."}],
        insight_schema(N_INSIGHTS), modelo)
    validos, fallidos = _partir(out.get("insights", []), month, company_id,
                                len(meses), catalogo, valores, unidades, set())
    mal_anchors = validar_anchors(out.get("anchor_analysis", []))
    anchors = out.get("anchor_analysis", [])

    if fallidos or mal_anchors:
        faltan = N_INSIGHTS - len(validos)
        resumen_ok = [f"{v['kind']}: {v['titulo']}" for v in validos]
        resumen_mal = [f"{f['kind']}: {f['motivo']}" for f in fallidos]
        if mal_anchors:
            resumen_mal.append(f"anchor_analysis: {mal_anchors}")
        out2 = llm.chat_json(
            [{"role": "system", "content": system},
             {"role": "user", "content":
              f"Vas bien: estos {len(validos)} YA quedaron y NO los repitas "
              f"ni regeneres: {resumen_ok}. Estos están mal, cada uno con "
              f"su motivo: {resumen_mal}.\n{catalogo_txt}\n{tabla}\nGenera "
              f"EXACTAMENTE {faltan} insights NUEVOS (kinds distintos a los "
              "válidos) que corrijan o reemplacen los fallidos, citando "
              "señales de esa lista (sin valor). Además repite "
              "anchor_analysis con los 4 comentarios "
              f"({', '.join(ANCHOR_METRICS)}) corregidos si estaban mal o "
              "idénticos si estaban bien."}],
            insight_schema(faltan), modelo)
        validos2, fallidos2 = _partir(
            out2.get("insights", []), month, company_id, len(meses),
            catalogo, valores, unidades, {v["kind"] for v in validos})
        validos.extend(validos2)
        fallidos = fallidos2
        if mal_anchors:
            mal_anchors = validar_anchors(out2.get("anchor_analysis", []))
            anchors = out2.get("anchor_analysis", [])

    if fallidos or len(validos) != N_INSIGHTS or mal_anchors:
        motivos = [f"{f.get('kind')}: {f.get('motivo')}" for f in fallidos]
        if mal_anchors:
            motivos.append(f"anchor_analysis: {mal_anchors}")
        raise ValueError(f"analista incompleto tras reintento "
                         f"({len(validos)}/{N_INSIGHTS}): {motivos}")
    orden = {"critical": 0, "warning": 1, "info": 2}
    validos.sort(key=lambda i: orden[i["severity"]])  # estable: conserva
    return {"month": month, "insights": validos,  # el rankeo del modelo
            "anchor_analysis": anchors,
            "tools_usados": [a["tool"] for a in audit],
            "truncado": truncado}


def _partir(items: list[dict], month: str, company_id: str,
            n_meses: int, catalogo: set[str], valores: dict,
            unidades: dict, vistos: set[str]) -> tuple[list[dict], list[dict]]:
    """Separa válidos (con id y valores reales) de fallidos (con motivo).

    vistos: kinds ya aceptados. Un kind repetido se rechaza (el unique
    company/month/kind de la tabla lo tumbaría al guardar).
    Evidencia con valor None (sin base en el motor) se rechaza.
    """
    validos, fallidos = [], []

    def _mal(i):
        kind = i.get("kind", "?")
        if kind in vistos:
            return "kind duplicado"
        motivo = validar_uno(i, n_meses, catalogo)
        if motivo:
            return motivo
        for e in (i.get("evidencia") or []):
            if valores.get(e["señal"]) is None:
                return (f"señal '{e['señal']}' sin valor en {month} "
                        "(sin base, no citar)")
        return None

    for i in items:
        motivo = _mal(i)
        if motivo is None:
            vistos.add(i["kind"])
            validos.extend(_con_ids([i], month, company_id, valores,
                                    unidades))
        else:
            fallidos.append({"kind": i.get("kind", "?"), "motivo": motivo,
                             "titulo": i.get("titulo", "")})
    return validos, fallidos
