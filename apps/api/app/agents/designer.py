"""Agente Diseñador (UI generativa, spec #22): insights -> tarjetas.

NO calcula ni analiza: recibe insights rankeados y elige componentes del
catálogo congelado. Datos faltantes los resuelve con get_metric /
metric_catalog (nunca inventa). Lo mecánico (alerta -> action_card) ya
viene resuelto en el payload de cada alerta; esto solo cubre lo ambiguo,
con fallback final a insight_text.
"""

from __future__ import annotations

import re

from app.agents import llm
from app.config import get_settings
from app.mcp import tools as T

DESIGNER_TOOLS = ["metric_catalog", "get_metric"]

#: Componentes reservados: se generan SIEMPRE por vía determinista
#: (reserved_cards) y el Diseñador tiene PROHIBIDO elegirlos.
RESERVED = ("tax_summary", "receipts_resolution", "receivables_resolution")

#: Máximo de tarjetas insight_text por diseño: el fallback existe pero
#: no es gratis (si el lote trae más, el excedente va al reintento).
MAX_TEXT = 2

#: Footnote para dueños no financieros: corto y sin tecnicismos.
MAX_FOOTNOTE = 140
JERGA = re.compile(
    r"\bHHI\b|\bDSO\b|\bburn\b|\brunway\b|\bvolatilidad\b|"
    r"puntos base|basis|amortización|apalancamiento|devengo|ebitda",
    re.IGNORECASE)

#: Iconos permitidos en action_card.icon (panel visual lateral).
#: El frontend mapea cada nombre a un icono Lucide; otro valor va al reintento.
ACTION_ICONS = ("receipt", "wallet", "flame", "piggy-bank",
                "trending-down", "file-warning", "landmark", "bell")

#: Guía por defecto kind -> componente (el modelo puede desviarse con
#: justificación en rationale).
KIND_HINTS = (
    "concentración/participación -> donut_total o bars_total; "
    "nivel/saldo/cifra única -> hero_number; "
    "serie temporal/tendencia -> metric_trend o time_series; "
    "ranking por partida -> progress_list; "
    "composición que suma/resta -> waterfall; "
    "varios porcentajes -> multi_ring; "
    "llamado a actuar -> action_card; "
    "solo texto/interpretación sin número -> insight_text."
)

DESIGNER_SYSTEM = """Eres el diseñador de UI financiera de MiNorte by Banorte.
Recibes insights rankeados y devuelves tarjetas del catálogo. Español simple.

Reglas duras:
- JAMÁS inventes cifras: cada número sale de get_metric (por nombre exacto
  del catálogo) o viene ya en el insight con evidencia.
- Si un nombre no existe, get_metric te devuelve el catálogo: úsalo, no adivines.
- Elige SOLO componentes de la lista permitida que recibes. Si ninguno calza,
  usa insight_text (texto + evidencia), que siempre funciona.
- Guía por defecto (salvo mejor opción justificada en rationale):
  concentración/participación -> donut_total o bars_total;
  nivel/saldo/cifra única -> hero_number;
  serie temporal/tendencia -> metric_trend o time_series;
  ranking por partida -> progress_list;
  composición que suma/resta -> waterfall;
  varios porcentajes -> multi_ring;
  listado de registros/filas (clientes, facturas, movimientos) -> data_table;
  llamado a actuar -> action_card;
  solo texto/interpretación sin número -> insight_text.
- Los componentes visuales aceptan footnote opcional para la explicación
  (1 frase, con cifras ya vistas): prefiere número + footnote sobre texto plano.
- El footnote lo lee un dueño que NO sabe de finanzas: español simple,
  máximo 140 caracteres, cero tecnicismos. PROHIBIDO: HHI, DSO, burn,
  runway, volatilidad, puntos base, basis, amortización, apalancamiento,
  devengo, EBITDA. Si el concepto es técnico, tradúcelo: en vez de
  "alta volatilidad en flujo diario" escribe "tu caja sube y baja mucho
  día con día"; en vez de "DSO alto" escribe "tus clientes tardan en
  pagarte". Mal: "El HHI de 0.28 indica concentración moderada".
  Bien: "Tus ingresos dependen de pocos clientes (28% en uno solo)".
- action_card acepta icon opcional (panel visual lateral): elige uno de
  receipt, wallet, flame, piggy-bank, trending-down, file-warning,
  landmark, bell según la alerta (gasto sin factura -> receipt,
  CxC -> wallet, riesgo de caja -> flame, impuestos -> landmark).
- Máximo 2 tarjetas insight_text por diseño: si necesitas más texto,
  es señal de que algún insight pide un componente visual.
- PROHIBIDO elegir tax_summary, receipts_resolution o receivables_resolution:
  esas tarjetas se generan automáticamente por vía determinista. Si un
  insight pide una de ellas, usa insight_text en su lugar.
- Respeta el component sugerido en el payload de cada alerta salvo que otro
  del catálogo exprese mejor el insight; justifícalo en rationale.
- Prioriza completitud sobre velocidad: mejor 2 llamadas con el dato que
  una tarjeta con huecos.
- Moneda MXN, fechas America/Mexico_City."""


def tool_defs():
    por_nombre = {t["name"]: t for t in T.TOOLS}
    return [llm.ToolDef(t["name"], t["description"], t["parameters"])
            for t in T.TOOLS if t["name"] in DESIGNER_TOOLS]


def _cards_schema(components: list[str], n: int | None = None,
                   min_items: int = 0) -> dict:
    item = {"type": "object",
            "properties": {
                "insight_id": {"type": "string"},
                "component": {"type": "string", "enum": sorted(components)},
                "props": {"type": "object"},
                "rationale": {"type": "string"}},
            "required": ["insight_id", "component", "props", "rationale"],
            "additionalProperties": False}
    arr: dict = {"type": "array", "items": item, "minItems": min_items}
    if n is not None:
        arr["minItems"] = n
        arr["maxItems"] = n
    return {"type": "object",
            "properties": {"cards": arr},
            "required": ["cards"], "additionalProperties": False}


# Espejo de apps/web/lib/ui-schema.ts (17 componentes congelados).
# Solo se exigen las requeridas; props extra se permiten (el registry
# del frontend ignora lo que no usa). Listas requeridas: no vacías.
_STR = "str"
_NUM = "num"

PROPS_SCHEMAS: dict[str, dict] = {
    "receivables_resolution": {"count": _NUM, "total": _STR},
    "receipts_resolution": {"count": _NUM, "total": _STR},
    "hero_number": {"label": _STR, "sublabel": _STR, "value": _STR},
    "multi_ring": {"items": [{"label": _STR, "value": _NUM}]},
    "bars_total": {"title": _STR, "total": _STR, "values": [_NUM],
                   "labels": [_STR]},
    "progress_list": {"title": _STR,
                      "items": [{"label": _STR, "percent": _NUM}]},
    "donut_total": {"title": _STR, "center_value": _STR,
                    "center_label": _STR,
                    "segments": [{"label": _STR, "value": _NUM}]},
    "entity_cluster": {"title": _STR, "subtitle": _STR,
                       "items": [{"name": _STR}]},
    "action_card": {"eyebrow": _STR, "title": _STR, "body": _STR,
                    "value": _STR, "action_label": _STR},
    "waterfall": {"title": _STR,
                  "bars": [{"label": _STR, "value": _NUM}]},
    "insight_text": {"title": _STR, "body": _STR},
    "time_series": {"title": _STR,
                    "points": [{"label": _STR, "income": _NUM,
                                "expenses": _NUM}],
                    "series": ("income", "expenses", "both")},
    "banorte_best_loans": {
        "amount": _STR,
        "options": [{"id": _STR, "nombre": _STR, "tasa_anual": _STR,
                     "pago_mensual": _STR, "costo_total": _STR,
                     "plazo_meses": _NUM}],
        "top_ids": [_STR]},
    "metric_trend": {"label": _STR, "value": _STR, "change": _STR,
                     "values": [_NUM]},
    "transactions_list": {
        "items": [{"id": _STR, "merchant": _STR, "category": _STR,
                   "date": _STR, "amount": _STR,
                   "type": ("ingreso", "egreso")}]},
    "timeline_list": {
        "items": [{"id": _STR, "customer_name": _STR,
                   "issued_at": _STR, "amount_pending": _STR,
                   "status": _STR, "due_date": (_STR, type(None))}]},
    "tax_summary": {"isr_estimado": _STR, "iva_neto": _STR,
                    "pct_deducible": _NUM},
    "financial_anchor": {"metric": _STR, "label": _STR,
                         "value": (_NUM, _STR, type(None)),
                         "analyst_comment": _STR},
    "data_table": {"title": _STR, "columns": [_STR],
                   "rows": [[(_STR, _NUM)]]},
}


def _es_num(v) -> bool:
    if isinstance(v, bool):
        return False
    if isinstance(v, (int, float)):
        return True
    try:
        float(str(v).replace(",", "").replace("$", "").replace("%", ""))
        return True
    except (ValueError, TypeError):
        return False


def _checa(valor, spec, ruta: str) -> str | None:
    """None si cumple; descripción del problema si no."""
    if isinstance(spec, tuple):  # enum de tipos o valores
        tipos = tuple(str if x == _STR else float if x == _NUM else x
                      for x in spec)
        if all(isinstance(x, type) for x in tipos):
            if isinstance(valor, bool):
                return f"{ruta} debe ser número o texto"
            if isinstance(valor, tipos):
                return None
            if float in tipos and _a_num(valor) is not None:
                return None
            nombres = " o ".join(x.__name__ for x in tipos)
            return f"{ruta} debe ser {nombres}"
        elif valor not in spec:
            return f"{ruta} debe ser uno de {list(spec)}, llegó {valor!r}"
        return None
    if spec == _STR:
        # Números donde va string se toleran (React los renderiza igual).
        return (None if isinstance(valor, (str, int, float))
                and not isinstance(valor, bool)
                else f"{ruta} debe ser str")
    if spec == _NUM:
        # "=ruta" es referencia a tabla de datos: la resuelve el llamador
        # (extra_check) antes de validar cifras; aquí solo pasa.
        if isinstance(valor, str) and valor.startswith("="):
            return None
        return None if _es_num(valor) else f"{ruta} debe ser número, llegó {valor!r}"
    if isinstance(spec, list):  # [subspec] = lista no vacía
        if not isinstance(valor, list) or not valor:
            return f"{ruta} debe ser lista no vacía"
        for j, el in enumerate(valor):
            if isinstance(spec[0], dict):
                if not isinstance(el, dict):
                    return f"{ruta}[{j}] debe ser objeto"
                for k, sub in spec[0].items():
                    if k not in el:
                        return f"{ruta}[{j}] sin {k}"
                    mal = _checa(el[k], sub, f"{ruta}[{j}].{k}")
                    if mal:
                        return mal
            else:
                mal = _checa(el, spec[0], f"{ruta}[{j}]")
                if mal:
                    return mal
        return None
    return f"{ruta}: spec desconocido"


def validate_choice(choice: dict, components: list[str]) -> list[str]:
    """Errores de una elección (vacío = válida). Sin LLM, testeable.

    Verifica componente del catálogo, props con la forma que el registry
    espera (espejo de ui-schema.ts) e insight_id para trazabilidad.
    Props extra se permiten.
    """
    errores = []
    comp = choice.get("component")
    if comp in RESERVED:
        return [f"{comp} es reservada (se genera automática, usa otra)"]
    if comp not in components:
        errores.append(f"component fuera de catálogo: {comp!r}")
        return errores
    props = choice.get("props")
    if not isinstance(props, dict):
        errores.append("props debe ser objeto")
        return errores
    spec = PROPS_SCHEMAS.get(comp, {})
    for campo, sub in spec.items():
        if campo not in props:
            errores.append(f"{comp} sin props.{campo}")
            continue
        mal = _checa(props[campo], sub, f"{comp}.{campo}")
        if mal:
            errores.append(mal)
    if comp == "action_card" and "icon" in props:
        if props["icon"] not in ACTION_ICONS:
            errores.append(f"action_card.icon debe ser uno de "
                           f"{list(ACTION_ICONS)}, llegó "
                           f"{props['icon']!r}")
    footnote = props.get("footnote")
    if isinstance(footnote, str):
        if len(footnote) > MAX_FOOTNOTE:
            errores.append(f"footnote de {len(footnote)} caracteres "
                           f"(máximo {MAX_FOOTNOTE}): acórtalo")
        elif JERGA.search(footnote):
            errores.append("footnote con tecnicismos: explícalo como a un "
                           "dueño que no sabe de finanzas")
    if not choice.get("insight_id"):
        errores.append("falta insight_id (trazabilidad)")
    errores.extend(_checa_consistencia(comp, props))
    return errores


def _checa_consistencia(comp: str, props: dict) -> list[str]:
    """Correspondencia label↔valor: la suma debe cuadrar con el total.

    Mata la falla vista en vivo (values [3,2,4,0,1] = índices de ranking
    en vez de montos, con total 98500): los números existían en el MCP
    pero no correspondían. Regla: sum(values) ≈ total.
    """
    if comp == "bars_total":
        total = _a_num(props.get("total"))
        vals = [v for v in (_a_num(x) for x in props.get("values", []))
                if v is not None]
        if total is not None and vals and len(vals) == len(props["values"]):
            if abs(sum(vals) - total) > max(1.0, abs(total) * 0.005):
                return [f"bars_total no cuadra: suman {sum(vals)} "
                        f"pero total dice {props.get('total')} "
                        "(values deben ser los montos, no índices)"]
        import re as _re
        texto = f"{props.get('title', '')} {props.get('footnote', '')}".lower()
        if (vals and len(vals) == len(props["values"])
                and _re.search(r"mayor|menor|top|ranking|reparte|ordena|concentra", texto)):
            tol = max(1.0, abs(total or 0.0) * 0.005)
            if any(b - a > tol for a, b in zip(vals, vals[1:])):
                return ["bars_total dice orden (mayor a menor) pero values "
                        "no van descendentes: reordena labels+values juntos"]
    if comp == "donut_total":
        centro = _a_num(props.get("center_value"))
        segs = [v for v in (_a_num(s.get("value"))
                            for s in props.get("segments", []))
                if v is not None]
        if centro is not None and segs and len(segs) == len(props["segments"]):
            if abs(sum(segs) - centro) > max(1.0, abs(centro) * 0.005):
                return [f"donut_total no cuadra: segmentos suman {sum(segs)} "
                        f"pero el centro dice {props.get('center_value')}"]
    return []


def _a_num(v):
    """Coacciona a número: tolera '$1,200', '45%' y cháchara ('casi 50'
    -> 50, primer número). Lo no convertible (None) lo rechaza el schema."""
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return v
    if isinstance(v, str):
        m = re.search(r"-?\d[\d,]*\.?\d*", v)
        if m:
            try:
                return float(m.group(0).replace(",", ""))
            except ValueError:
                return None
    return None


def _normalizar(choice: dict) -> None:
    """Convierte strings numéricos a número in-place (el modelo manda
    '45%' o '$1,200'; el registry ya coacciona, pero el schema pide número).
    Lo no convertible se deja y la validación lo rechaza con motivo."""

    def _rec(valor, spec):
        if spec == _NUM:
            n = _a_num(valor)
            return n if n is not None else valor
        if isinstance(spec, list) and isinstance(valor, list):
            if spec and isinstance(spec[0], dict):
                # Poda items sin claves requeridas (el modelo a veces omite
                # una clave; mejor tarjeta incompleta que tarjeta rota).
                req = set(spec[0])
                podados = [el for el in valor
                           if isinstance(el, dict) and req <= set(el)]
                return [_rec(el, spec[0]) for el in podados] if podados else valor
            return [_rec(el, spec[0]) for el in valor] if spec else valor
        if isinstance(spec, dict) and isinstance(valor, dict):
            return {k: (_rec(v, spec[k]) if k in spec else v)
                    for k, v in valor.items()}
        return valor

    comp = choice.get("component")
    props = choice.get("props")
    spec = PROPS_SCHEMAS.get(comp, {})
    if isinstance(props, dict) and spec:
        for campo, sub in spec.items():
            if campo in props:
                props[campo] = _rec(props[campo], sub)


def _partir(cards: list[dict], components: list[str],
            extra_check=None, max_text: int = MAX_TEXT):
    validas, fallidas = [], []
    n_texto = 0
    for c in cards:
        _normalizar(c)
        errs = validate_choice(c, components)
        if extra_check:
            errs = errs + extra_check(c)
        if not errs and c.get("component") == "insight_text":
            n_texto += 1
            if n_texto > max_text:
                errs = [f"tope de {max_text} insight_text excedido: "
                        "usa un componente visual con footnote"]
        if errs:
            fallidas.append({"insight_id": c.get("insight_id", "?"),
                             "component": c.get("component", "?"),
                             "motivos": errs})
        else:
            validas.append(c)
    return validas, fallidas


def design(insights: list[dict], components: list[str],
           executor=None, model: str | None = None,
           brief: str = "", exact: bool = True,
           partial: bool = False, extra_check=None,
           max_text: int = MAX_TEXT, min_cards: int = 0) -> dict:
    """Insights rankeados -> [{insight_id, component, props, rationale}].

    components: catálogo congelado (viene de ui-schema.ts, no hardcodeado).
    Fase 1 (tools): el modelo pide vía get_metric lo que le falte.
    Fase 2 (JSON estricto): elige componentes solo del catálogo.
    exact=True: 1:1 insight -> tarjeta (lo faltante va al reintento).
    exact=False (consultant_view): cantidad libre, las que hagan falta.
    brief: instrucción extra del llamador (p. ej. incluir relacionadas).
    partial=True: si algo sigue fallando tras el reintento, devuelve las
    válidas en vez de lanzar (consultant_view prefiere algo a nada).
    extra_check(choice)->[errores]: validación extra del llamador
    (p. ej. cifras contra MCP); sus errores van al reintento igual.
    """
    from app.mcp import tools as _T

    # Mini ejecuta tools; flagship elige (el mini ignora el tope de texto
    # y los tipos aun con el error explícito en el reintento).
    gather_modelo = model or llm.tool_model()
    elige_modelo = model or get_settings().OPENAI_REASONING_MODEL
    base = ("Insights (id, severidad, texto, evidencia):\n" +
            "\n".join(f"- {i.get('id')}: [{i.get('severity')}] {i.get('titulo')} | "
                       f"{i.get('detalle')} | evidencia={i.get('payload', {})}"
                       for i in insights) +
            f"\nComponentes permitidos: {', '.join(sorted(components))}" +
            (f"\nInstrucción del llamador: {brief}" if brief else ""))
    defs = [llm.ToolDef(t["name"], t["description"], t["parameters"])
            for t in _T.TOOLS if t["name"] in ("metric_catalog", "get_metric")]
    gather, audit, _ = llm.run_tool_loop(
        DESIGNER_SYSTEM + "\nFase 1: pide con get_metric todo número que te "
        "falte para elegir bien. No elijas aún.",
        [{"role": "user", "content": base}], defs,
        executor or _T.execute, gather_modelo, temperature=0.2)
    def _forma(sub, prof=0) -> str:
        if isinstance(sub, dict):
            dentro = ", ".join(f"{k}{_forma(v, prof + 1)}" for k, v in sub.items())
            return f"{{{dentro}}}" if prof else ""
        if isinstance(sub, list):
            return f"[]{_forma(sub[0], prof + 1)}" if sub else "[]"
        return ""

    system2 = (DESIGNER_SYSTEM +
               "\nRespeta estos schemas de props por componente "
               "(listas no vacías, montos como string, "
               "series/periodos como número; objetos e items anidados con "
               "TODAS sus claves). footnote opcional (1 frase) "
               "en multi_ring, bars_total, progress_list, donut_total, "
               "entity_cluster, waterfall, metric_trend y time_series:\n" +
               "\n".join(f"- {c}: requeridas {sorted(PROPS_SCHEMAS[c])}"
                         + _forma({k: v for k, v in PROPS_SCHEMAS[c].items()
                                   if isinstance(v, (dict, list))})
                         for c in sorted(components) if c in PROPS_SCHEMAS))
    out = llm.chat_json(
        [{"role": "system", "content": system2},
         {"role": "user", "content": base + "\n\nDatos extra:\n" + gather}],
        _cards_schema(components, min_items=0 if exact else min_cards),
        elige_modelo, strict=False)
    validas, fallidas = _partir(out.get("cards", []), components,
                                extra_check, max_text)
    if exact:
        # 1:1 insight -> tarjeta: lo no cubierto va al reintento como
        # faltante (salvo que ya esté fallido por otro motivo).
        esperados = [i.get("id") for i in insights]
        cubiertos = {c["insight_id"] for c in validas}
        ya_fallidos = {f["insight_id"] for f in fallidas}
        for iid in esperados:
            if iid not in cubiertos and iid not in ya_fallidos:
                fallidas.append({"insight_id": iid, "component": "?",
                                 "motivos": ["sin tarjeta para este insight"]})

    if fallidas:
        ok = [(c["insight_id"], c["component"]) for c in validas]
        mal = [(f["insight_id"], f["component"], f["motivos"])
               for f in fallidas]
        out2 = llm.chat_json(
            [{"role": "system", "content": system2},
             {"role": "user", "content":
              base + "\n\nDatos extra:\n" + gather +
              f"\nVas bien: estas {len(validas)} YA quedaron y NO las repitas "
              f"ni regeneres: {ok}. Estas {len(fallidas)} están mal, cada "
              f"una con su motivo: {mal}. Genera EXACTAMENTE "
              f"{len(fallidas)} tarjetas NUEVAS que las reemplacen "
              "(mismo insight_id, componente y props corregidos, "
              "con la forma de props indicada arriba)."}],
            _cards_schema(components, len(fallidas)), elige_modelo,
            strict=False)
        validas2, fallidas2 = _partir(out2.get("cards", []), components,
                                      extra_check, max_text)
        ids_ok = {c["insight_id"] for c in validas}
        for c in validas2:
            if c["insight_id"] in ids_ok:
                fallidas2.append({"insight_id": c["insight_id"],
                                  "component": c["component"],
                                  "motivos": ["insight_id duplicado "
                                              "de una válida"]})
            else:
                validas.append(c)
        fallidas = fallidas2

    if fallidas:
        if partial and validas:
            import sys as _sys
            print(f"[warn] design parcial: {len(validas)} válidas, "
                  f"se omiten {len(fallidas)}: {fallidas}"[:300],
                  file=_sys.stderr)
            return {"cards": validas,
                    "tools_usados": [a["tool"] for a in audit]}
        raise llm.LLMError(f"elección inválida tras reintento: {fallidas}")
    return {"cards": validas,
            "tools_usados": [a["tool"] for a in audit]}


def reserved_cards(month: str, executor=None) -> list[dict]:
    """Las 3 tarjetas SIEMPRE visibles, vía determinista (sin LLM).

    tax_summary sale de get_signals; receipts/receivables de las alertas
    (misma fuente que /api/alerts). Si un dato falta (mes vacío), esa
    tarjeta se omite en vez de inventarse. Formato listo para DynamicUI:
    [{insight_id, component, props, rationale}].
    """
    from app.mcp import tools as _T

    ex = executor or _T.execute
    a, m = map(int, month.split("-"))
    cards: list[dict] = []

    sig = ex("get_signals", {"month": month}).get("signals", {})
    isr, iva, pct = (sig.get("isr_estimado"), sig.get("iva_neto"),
                     sig.get("pct_gasto_deducible"))
    if (isr is not None and iva is not None and pct is not None
            and sig.get("tiene_datos")):
        cards.append({
            "insight_id": f"{month}_fiscal", "component": "tax_summary",
            "props": {"isr_estimado": str(isr), "iva_neto": str(iva),
                      "pct_deducible": float(str(pct))},
            "rationale": "reservada: resumen fiscal determinista"})

    from app import data as _data
    from app.config import get_settings as _gs
    from app.financial import alerts as _al
    try:
        al = _al.generar_alertas(_data.get_transactions(), _data.get_cfdis(),
                                 _data.get_matches(), a, m,
                                 _gs().COMPANY_ID)
    except Exception:
        al = []
    for alerta in al:
        pay = alerta.get("payload") or {}
        if pay.get("component") in ("receipts_resolution",
                                    "receivables_resolution"):
            cards.append({
                "insight_id": alerta["id"], "component": pay["component"],
                "props": pay["props"],
                "rationale": f"reservada: alerta {alerta['rule']}"})
    return cards
