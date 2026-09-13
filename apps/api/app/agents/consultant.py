"""Consultor Financiero (spec #3.4): interpreta, nunca calcula.

Responde sobre el negocio usando SOLO tools (números del motor).
El modelo redacta; los montos siempre vienen de tools.
"""

from __future__ import annotations

import re

from app.agents import llm
from app.mcp import tools as T

SYSTEM = """Eres el consultor financiero de una PyME mexicana, dentro de la app MiNorte by Banorte.
Hablas español simple, sin jerga contable, como un asesor de confianza, no como un ERP.

Reglas duras:
- JAMÁS calcules ni inventes cifras: todo número sale de llamar tools primero.
- Evaluación de gastos (empleado, mercancía, auto, terreno, construcción, renta,
  maquinaria): UNA sola ruta. 1) Detecta el tipo. 2) Llama get_variables_gasto
  con ese tipo. 3) Mapea lo que el usuario ya dijo. 4) Pregunta SOLO lo faltante,
  a medida del tipo, máximo 2 rondas; si no lo dan, no avances. 5) Llama
  evaluar_gasto con lo mapeado. 6) Narra el veredicto citando desembolso,
  mensualidad, cobertura y supuestos declarados. Prohibido elegir otra tool
  de simulación: no existen.
- Cita las cifras exactas que devuelven las tools.
- Futuro (proyecciones, 'próximo mes', 'qué viene'): SOLO vía
  project_next_month. Sin llamarla, PROHIBIDO proyectar: di que no hay
  proyección y ofrece calcularla. Al darla, declara método, confianza y
  supuestos, y marca cada cifra como estimada, nunca como dato.
- PROHIBIDO dibujar gráficas o tablas con caracteres en el texto
  (barras █▓, tablas ASCII con pipes): para lo visual están las
  tarjetas; el texto interpreta y explica, no dibuja.
- Si falta un dato, dilo y pide lo mínimo necesario.
- Respuestas cortas (~120 palabras) salvo que pidan detalle.
- Moneda MXN, fechas America/Mexico_City.
- FORMATO DE CIFRAS (obligatorio, sin excepción):
  separador de miles con coma y hasta 4 decimales, con el punto como
  separador decimal: $1,234,567.8912 · $11,690.00 · 21.8934%.
  Escribe los decimales que traiga el valor de la tool, hasta un máximo de
  4; no los recortes a 0 ni a 2, y no rellenes con ceros que la tool no dio
  más allá de los centavos. Nunca notación científica ni cifras pegadas sin
  comas (mal: $120092.17; bien: $120,092.17). Esto NO te autoriza a inventar
  precisión: el número sigue siendo el que devolvió la tool, solo cambia
  cómo lo escribes.
- Investigación por niveles (progresiva, como un contador):
  Nivel 0 = signals/brief (totales por rubro con n_negocios y hints).
  Nivel 1 = get_merchants (filtra por rubro/monto, trae 10, 50 o todos).
  Nivel 2 = get_merchant_detail (serie mensual + recurrencia de un comercio).
  Profundiza cuando (a) pregunten un quién/cuál específico, (b) un hint_drill
  lo sugiera, o (c) el top agregado no explique el grueso del rubro.
  Prioriza completitud sobre velocidad: mejor 2 llamadas con el dato que
  una respuesta sin él. Pero si ya tienes los datos para responder, responde:
  no explores por explorar (cada llamada reenvía toda la conversación).
-   Lista vacía de un tool = filtros muy estrictos, NO ausencia de datos:
  reintenta sin rubro o con limit mayor antes de decir "no hay".
  Preguntas de cobertura se responden del rango con datos (ver contexto),
  sin inventar.
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
        txns = _data.get_transactions()
        fechas = sorted(t.date for t in txns)
        primero = f"{fechas[0].year}-{fechas[0].month:02d}"
        ultimo = f"{fechas[-1].year}-{fechas[-1].month:02d}"
    except Exception:
        primero, ultimo = "s/d", "2026-08"
    return (f"\nHoy es {_date.today().isoformat()} (America/Mexico_City). "
            f"Los datos cubren {primero} a {ultimo}. "
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
    "get_months_with_data", "project_next_month",
    "get_open_receivables", "get_variables_gasto", "evaluar_gasto",
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
    """Una pregunta. Devuelve {respuesta, tools_usados, truncado, tarjetas}.

    tarjetas: 0-1 UISchemas del Diseñador para el consultant_view ([] si no
    hubo tools — sin datos no hay tarjeta — o si el diseño falla).
    """
    respuesta, audit, truncado = llm.run_tool_loop(
        SYSTEM + _contexto() + _perfil_block(perfil),
        (history or []) + [{"role": "user", "content": texto}],
        tool_defs(), executor or T.execute,
        model or llm.tool_model(), temperature=0.2, max_steps=5)
    llamadas = [{"tool": a["tool"], "args": a.get("args", {})} for a in audit]
    ex = executor or T.execute
    resultados = _releer_tools(audit, ex)
    if resultados:
        respuesta = _corregir_cifras(texto, respuesta, resultados,
                                     model or llm.tool_model())
    return {"respuesta": respuesta,
            "tools_usados": [a["tool"] for a in audit],
            "llamadas": llamadas,
            "truncado": truncado,
            "tarjetas": _tarjetas(texto, respuesta, bool(audit), ex,
                                  resultados)}


def _formatear_como(valor: float, token: str) -> str:
    """98500.0 como '99,000' -> '98,500'; como '99,000.00' -> '98,500.00'."""
    dec = len(token.split(".")[1]) if "." in token else 0
    txt = f"{valor:,.{dec}f}" if "," in token else (
        f"{valor:.{dec}f}" if dec else str(int(round(valor))))
    return txt


def _corregir_cifras(pregunta: str, respuesta: str,
                     resultados: list[dict],
                     modelo: str | None) -> str:
    """Corrige montos del texto que no están en salidas MCP.

    1) Determinista: token erróneo con UN único candidato en base dentro
       de ±5% -> se sustituye con su formato (sin LLM).
    2) Si no, una reescritura barata con la lista de valores válidos.
    3) Si persiste, se queda el original y se loguea (nunca se bloquea).
    """
    mal = cifras_texto(respuesta, resultados)
    if not mal:
        return respuesta
    base: set[float] = set()
    _juntar_montos(resultados, base)
    nueva = respuesta
    pendientes = []
    for tok in mal:
        w = _normalizar_cifra(tok.replace("$", ""))
        cands = [b for b in base
                 if w and abs(b - w) / max(abs(w), 1e-9) <= 0.05] \
            if w else []
        if len(cands) == 1:
            fijo = _formatear_como(cands[0], tok)
            if tok.startswith("$") and not fijo.startswith("$"):
                fijo = "$" + fijo
            import sys as _sys0
            print(f"[info] cifra corregida: {tok} -> {fijo}"[:80],
                  file=_sys0.stderr)
            nueva = nueva.replace(tok, fijo, 1)
        else:
            pendientes.append(tok)
    if not pendientes:
        return nueva
    validas = sorted(base)[:30]
    try:
        r = llm.chat(
            [{"role": "user", "content":
              f"Reescribe esta respuesta cambiando ÚNICAMENTE las cifras "
              f"erróneas ({'; '.join(f'cifra {t} no está en los datos' for t in pendientes)}). "
              f"Usa SOLO cifras de esta lista "
              f"de valores válidos (cópialas exacto, no redondees; "
              f"si alguna marcada ya es correcta, consérvala; no "
              f"toques nada más): {validas}\n\n"
              f"Pregunta: {pregunta}\nRespuesta:\n{nueva}"}],
            model=modelo)
        texto = (r.content or "").strip()
        if texto and not cifras_texto(texto, resultados):
            return texto
    except Exception as e:
        import sys as _sys
        print(f"[warn] reescritura omitida: {type(e).__name__}"[:80],
              file=_sys.stderr)
    import sys as _sys2
    print(f"[warn] texto con cifras sin verificar: {pendientes}"[:160],
          file=_sys2.stderr)
    return nueva


def _releer_tools(audit: list[dict], executor) -> list[dict]:
    """Re-ejecuta las tools del turno (deterministas, sin LLM) para tener
    los valores reales contra los que validar las cifras de las tarjetas."""
    vistos, resultados = set(), []
    import json as _json
    for a in audit:
        llave = (a.get("tool"), _json.dumps(a.get("args", {}), sort_keys=True,
                                            default=str))
        if llave in vistos:
            continue
        vistos.add(llave)
        try:
            resultados.append({"tool": a.get("tool"),
                               "resultado": executor(a.get("tool"),
                                                     a.get("args", {}))})
        except Exception:
            continue
    return resultados


_NUMERO = re.compile(r"-?\d[\d,]*\.?\d*")
_MONTO = re.compile(r"\$?-?\d{1,3}(?:,\d{3})+(?:\.\d+)?|\$?-?\d+\.\d+")


def cifras_texto(texto: str, resultados: list[dict]) -> list[str]:
    """Cifras tipo monto en prosa deben existir verbatim en salidas MCP.

    Solo tokens con decimales o separador de miles (así años, días, folios
    y conteos no dan falsos positivos). Devuelve los TOKENS erróneos
    ($100,000 vs $98,500 real -> ['$100,000']).
    """
    base: set[float] = set()
    _juntar_montos(resultados, base)
    errores = []
    for tok in _MONTO.findall(texto):
        n = _normalizar_cifra(tok.replace("$", ""))
        if n is not None and n not in base:
            errores.append(tok)
    return errores


def _juntar_montos(v, base: set[float]) -> None:
    """Base solo con montos (mismo regex que el texto): fragmentos de fecha
    ('00' de un timestamp) o años nunca entran, así un total 0.0 inventado
    no pasa por coincidir con un ':00'."""
    if isinstance(v, str):
        for tok in _MONTO.findall(v):
            n = _normalizar_cifra(tok.replace("$", ""))
            if n is not None:
                base.add(n)
    elif isinstance(v, dict):
        for x in v.values():
            _juntar_montos(x, base)
    elif isinstance(v, list):
        for x in v:
            _juntar_montos(x, base)


def _normalizar_cifra(tok: str):
    try:
        return float(tok.replace(",", ""))
    except (ValueError, TypeError):
        return None


def validar_cifras(choice: dict, resultados: list[dict]) -> list[str]:
    """Toda cifra de props/footnote debe existir verbatim en salidas MCP.

    Normaliza ($, comas, MXN, %) y compara numéricamente. Lo que no está
    en los datos va al reintento con la cifra exacta como motivo.
    """
    textos: list[str] = []

    def _juntar(v):
        if isinstance(v, str):
            textos.append(v)
        elif isinstance(v, dict):
            for x in v.values():
                _juntar(x)
        elif isinstance(v, list):
            for x in v:
                _juntar(x)

    props = choice.get("props") or {}
    _juntar(props)
    if isinstance(props.get("footnote"), str):
        textos.append(props["footnote"])
    base: set[float] = set()
    _juntar_base(resultados, base)
    errores = []
    for t in textos:
        for tok in _NUMERO.findall(t):
            n = _normalizar_cifra(tok)
            if n is not None and n not in base:
                errores.append(f"cifra {tok} no está en los datos "
                               "(copia el valor exacto de las tools)")
    return errores


def _juntar_base(v, base: set[float]) -> None:
    if isinstance(v, str):
        for tok in _NUMERO.findall(v):
            n = _normalizar_cifra(tok)
            if n is not None:
                base.add(n)
    elif isinstance(v, dict):
        for x in v.values():
            _juntar_base(x, base)
    elif isinstance(v, list):
        for x in v:
            _juntar_base(x, base)


_SIN_CIFRA = {"id", "insight_id", "uuid", "cfdi_uuid"}

_RUIDO = {"uuid", "cfdi_uuid", "id", "conversation_id", "company_id",
          "transaction_id", "match_id"}


def tabla_datos(resultados: list[dict], tope: int = 60) -> tuple[str, dict]:
    """Aplana resultados MCP a líneas 'ruta = valor' (sin UUIDs ni ruido).

    Devuelve (texto, mapa) para que el modelo cite rutas (=ruta) y el
    código las sustituya: copiar lo hace el sistema, no el modelo.
    """
    lineas: list[str] = []
    mapa: dict[str, str] = {}

    def _bajar(v, ruta):
        if len(lineas) >= tope:
            return
        if isinstance(v, dict):
            for k, x in v.items():
                if k not in _RUIDO:
                    _bajar(x, f"{ruta}.{k}" if ruta else str(k))
        elif isinstance(v, list):
            for j, x in enumerate(v):
                _bajar(x, f"{ruta}[{j}]")
        elif isinstance(v, (str, int, float)) and not isinstance(v, bool):
            lineas.append(f"{ruta} = {v}")
            mapa[ruta] = str(v)

    for r in resultados:
        _bajar(r.get("resultado"), str(r.get("tool")))
    return "\n".join(lineas), mapa


def resolver_citas(choice: dict, mapa: dict) -> list[str]:
    """Sustituye '=ruta' por el valor real de la tabla (in-place).

    Ruta desconocida -> error al reintento. Así el modelo selecciona QUÉ
    mostrar y el código pone CUÁNTO: inventar o evadir es imposible.
    """
    errores: list[str] = []

    def _rec(v):
        if isinstance(v, str) and v.startswith("="):
            ruta = v[1:]
            if ruta in mapa:
                return mapa[ruta]
            errores.append(f"cita ={ruta} no existe en payload.tabla")
            return v
        if isinstance(v, dict):
            return {k: _rec(x) for k, x in v.items()}
        if isinstance(v, list):
            return [_rec(x) for x in v]
        return v

    props = choice.get("props")
    if isinstance(props, dict):
        choice["props"] = _rec(props)
    return errores
    """Aplana resultados MCP a líneas 'ruta = valor' (sin UUIDs ni ruido).

    Tabla corta y copiable para que el modelo cite exacto en vez de evadir.
    """
    lineas: list[str] = []

    def _bajar(v, ruta):
        if len(lineas) >= tope:
            return
        if isinstance(v, dict):
            for k, x in v.items():
                if k not in _RUIDO:
                    _bajar(x, f"{ruta}.{k}" if ruta else str(k))
        elif isinstance(v, list):
            for j, x in enumerate(v):
                _bajar(x, f"{ruta}[{j}]")
        elif isinstance(v, (str, int, float)) and not isinstance(v, bool):
            lineas.append(f"{ruta} = {v}")

    for r in resultados:
        _bajar(r.get("resultado"), str(r.get("tool")))
    return "\n".join(lineas)


def tiene_cifra(choice: dict) -> list[str]:
    """Una tarjeta de consulta sin ninguna cifra es evasión ('No disponible'):
    se rechaza para que el reintento copie el dato real."""
    props = choice.get("props") or {}

    def _hay(v, clave=""):
        if isinstance(v, str):
            return clave not in _SIN_CIFRA and bool(_NUMERO.search(v))
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            return True
        if isinstance(v, dict):
            return any(_hay(x, k) for k, x in v.items())
        if isinstance(v, list):
            return any(_hay(x, clave) for x in v)
        return False

    if _hay(props):
        return []
    return ["tarjeta sin ninguna cifra: copia el valor exacto de "
            "payload.datos, prohibido 'No disponible'"]


def _tarjetas(pregunta: str, respuesta: str, con_datos: bool,
              executor, resultados: list[dict] | None = None) -> list[dict]:
    """Tarjetas que visualizan la respuesta (cantidad libre, [] si no aplica).

    Sin datos (sin tools) o fallo de diseño -> []. Usa el catálogo existente
    (firmas PROPS_SCHEMAS) y puede incluir relacionadas: contexto o datos
    curiosos con base que ayuden a entender la respuesta.
    """
    if not con_datos:
        return []
    from app.agents import designer as D

    tabla, mapa = tabla_datos(resultados or [])
    pide_tabla = any(w in pregunta.lower()
                     for w in ("tabla", "listado", "lista", "desglosa",
                               "detalle por", "quiénes", "quienes"))
    pseudo = [{"id": "consulta", "severity": "info",
               "titulo": pregunta[:120], "detalle": respuesta[:400],
               "payload": {"kind": "consulta", "evidencia": [],
                           "tabla": tabla}}]
    # Consultas: puro visual (insight_text prohibido: el texto de la
    # respuesta ya explica; la tarjeta debe mostrar, no repetir).
    componentes = [c for c in D.PROPS_SCHEMAS
                   if c not in D.RESERVED + ("insight_text",)]

    def _cifras(choice: dict) -> list[str]:
        return (resolver_citas(choice, mapa) or tiene_cifra(choice)
                or validar_cifras(choice, resultados or []))
    componentes = [c for c in D.PROPS_SCHEMAS if c not in D.RESERVED]

    try:
        out = D.design(
            pseudo, componentes, executor=executor, exact=False,
            partial=True, extra_check=_cifras, max_text=1, min_cards=4,
            brief=("Responde visualmente la pregunta con MÍNIMO 4 tarjetas, "
                   "sin límite máximo: la respuesta directa (tabla o "
                   "detalle) más relacionadas con datos que ya existen "
                   "(volatilidad, concentración, DSO, antigüedad, runway, "
                   "margen...). "
                   "Todas con las firmas del catálogo. Prioriza componentes "
                   "visuales (números, gráficas, rankings); insight_text "
                   "máximo 1 y solo si nada visual calza. "
                   + ("El usuario pidió explícitamente una TABLA: usa "
                      "data_table con columns y rows. " if pide_tabla else "")
                   + "Para CADA cifra en "
                   "props escribe la ruta de payload.tabla con = inicial "
                   "(p. ej. value: '=get_open_receivables.total'); el "
                   "sistema la sustituye por el valor exacto. Prohibido "
                   "escribir cifras a mano o 'No disponible'."))
    except Exception as e:
        import sys as _sys
        print(f"[warn] tarjetas consulta omitidas: {type(e).__name__}: {e}"[:600],
              file=_sys.stderr)
        return []
    return out.get("cards", [])
