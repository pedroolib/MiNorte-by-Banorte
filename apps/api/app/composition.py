"""Composition Engine (Generative Dashboard UI): combina determinista +
interpretación en JSON listo para renderizar. Sin frontend: devuelve JSON.

Pipeline: Financial Engine -> candidatos deterministas + Analista
(insights + anchor_analysis) -> composición (anchors + actions +
discovery + summary) -> UI Schema JSON -> React (DynamicUI).

Reglas de producto:
- 4 anchors siempre (con comentario del Analista, números del motor).
- tax_summary NO se incluye como tarjeta (sus números viven en el anchor
  de impuesto estimado); receipts/receivables SOLO si hay algo que resolver.
- Si hay acciones pendientes, al menos 1 entra (precedencia sobre discovery).
- Discovery rota semanal con scoring auditable + diversidad (máx 2/familia).
- Sin problemas: 4 anchors + 4-5 discovery, sin placeholders ni vacías.
"""

from __future__ import annotations

from datetime import date, datetime, timezone

from app.agents import designer as D
from app.agents import llm
from app.config import get_settings

ANCHOR_DEFS = (
    ("revenue", "Ventas", "ventas"),
    ("profit", "Utilidad", "utilidad"),
    ("cash", "Balance", "efectivo"),
    ("estimated_tax", "Impuesto estimado", "isr_estimado"),
)

_SEV = {"critical": 5, "warning": 3, "info": 1}
_IMP = {"high": 3, "medium": 2, "low": 1}


def week_id(hoy: date | None = None) -> str:
    hoy = hoy or date.today()
    iso = hoy.isocalendar()
    return f"{iso.year}-W{iso.week:02d}"


def prev_month(month: str) -> str:
    a, m = map(int, month.split("-"))
    m -= 1
    if m == 0:
        a, m = a - 1, 12
    return f"{a}-{m:02d}"


def _num(v):
    try:
        return float(str(v).replace(",", ""))
    except (ValueError, TypeError):
        return None


def anchors(month: str, ex, comments: dict) -> list[dict]:
    """4 anclas: números del motor (get_metric actual+previo) + comentario.

    Trend % calculado en código; sin mes previo con datos -> trend null.
    """
    out = []
    for metric, label, signal in ANCHOR_DEFS:
        cur, prv = None, None
        try:
            cur = _num(ex("get_metric", {"name": signal,
                                         "month": month}).get("value"))
        except Exception:
            cur = None
        try:
            prv = _num(ex("get_metric", {"name": signal,
                                         "month": prev_month(month)})
                       .get("value"))
        except Exception:
            prv = None
        trend = None
        if cur is not None and prv:
            pct = round((cur - prv) / abs(prv) * 100, 1)
            trend = {"direction": "up" if pct > 0 else
                     "down" if pct < 0 else "flat",
                     "percentage": abs(pct)}
        out.append({"metric": metric, "label": label, "value": cur,
                    "trend": trend,
                    "analyst_comment": comments.get(metric, "")})
    return out


def fingerprint(kind: str, evidencia: list[dict]) -> str:
    bits = ";".join(f"{e.get('señal')}={e.get('valor')}"
                    for e in (evidencia or []))
    return f"{kind}|{bits}"


def _semanas_atras(exp: list[dict], semanas: int,
                   hoy: datetime | None = None) -> set[str]:
    """Kinds mostrados en las últimas N semanas."""
    hoy = hoy or datetime.now(timezone.utc)
    kinds = set()
    for e in exp:
        try:
            visto = e.get("shown_at", "")
            dt = (datetime.fromisoformat(str(visto).replace("Z", "+00:00"))
                  if isinstance(visto, str) else visto)
            if (hoy - dt).days < semanas * 7:
                kinds.add(e.get("insight_kind"))
        except Exception:
            continue
    return kinds


def score(item: dict, exposures: list[dict],
          hoy: datetime | None = None) -> tuple[float, dict]:
    """Scoring auditable del spec. Devuelve (score, desglose)."""
    ultima = _semanas_atras(exposures, 1, hoy)
    recientes = _semanas_atras(exposures, 3, hoy)
    fp = fingerprint(item.get("kind", ""), item.get("evidencia", []))
    ultimo_fp = next((e.get("insight_fingerprint") for e in exposures
                      if e.get("insight_kind") == item.get("kind")), "")
    partes = {
        "severity": _SEV.get(item.get("severity"), 0),
        "financial_impact": _IMP.get(item.get("financial_impact"), 0),
        "actionability": 2 if item.get("actionability") == "high" else 0,
        "novelty": 2 if item.get("kind") not in recientes else 0,
        "recent_change": 2 if (ultimo_fp and fp != ultimo_fp) else 0,
        "repetition_penalty": -3 if item.get("kind") in ultima else 0,
    }
    return sum(partes.values()), partes


def discover(pool: list[dict], exposures: list[dict], n: int,
             hoy: datetime | None = None, wid: str | None = None) -> list[dict]:
    """Top-n por score con diversidad (máx 2 por familia salvo critical).

    Rotación dura: los kinds de la semana ANTERIOR (por week_id, no por
    fecha: regenerar varias semanas el mismo día no debe confundirla)
    no repiten, salvo que el pool no alcance (se rellena por score).
    """
    if wid:
        previas = sorted({e.get("week_id", "") for e in exposures
                          if e.get("week_id", "") < wid})
        ultima = {e.get("insight_kind") for e in exposures
                  if e.get("week_id") == (previas[-1] if previas else None)}
    else:
        ultima = _semanas_atras(exposures, 1, hoy)
    frescos = [it for it in pool if it.get("kind") not in ultima]
    base = frescos if len(frescos) >= n else pool
    rank = sorted(((score(it, exposures, hoy)[0], it) for it in base),
                  key=lambda t: -t[0])
    elegidos, por_familia = [], {}
    for _, it in rank:
        fam = it.get("family", "operations")
        if (por_familia.get(fam, 0) >= 2
                and it.get("severity") != "critical"):
            continue
        por_familia[fam] = por_familia.get(fam, 0) + 1
        elegidos.append(it)
        if len(elegidos) == n:
            break
    if len(elegidos) < n:
        # Pool corto: rellena con lo mejor aunque repita (sin duplicar
        # y respetando diversidad).
        vistos = {id(it) for it in elegidos}
        resto = sorted(((score(it, exposures, hoy)[0], it) for it in pool
                        if id(it) not in vistos), key=lambda t: -t[0])
        for _, it in resto:
            if len(elegidos) == n:
                break
            fam = it.get("family", "operations")
            if (por_familia.get(fam, 0) >= 2
                    and it.get("severity") != "critical"):
                continue
            por_familia[fam] = por_familia.get(fam, 0) + 1
            elegidos.append(it)
    return elegidos


def huella(pool: list[dict], month: str) -> str:
    """Fingerprint de los insumos: si cambia, el caché semanal caduca.

    Incluye mes, cantidad y marca temporal máxima: re-correr el Analista
    (aunque dé los mismos 10 kinds) invalida composiciones viejas.
    """
    marcas = [str(it.get("updated_at") or it.get("created_at") or "")
              for it in pool]
    return f"{month}:{len(pool)}:{max(marcas) if marcas else ''}"


def _para_disenar(items: list[dict]) -> list[dict]:
    return [{"id": it.get("id") or it.get("kind"),
             "severity": it.get("severity", "info"),
             "titulo": it.get("titulo", ""), "detalle": it.get("detalle", ""),
             "payload": {"kind": it.get("kind"),
                         "evidencia": it.get("evidencia", [])}}
            for it in items]


def weekly_summary(cards: list[dict], month: str,
                   model: str | None = None) -> str:
    """Resumen corto que conecta lo visible. Chat barato sin tools."""
    s = get_settings()
    lineas = "\n".join(
        f"- [{c.get('component')}] {c.get('props', {})}" for c in cards)
    r = llm.chat(
        [{"role": "user", "content":
          f"Resume en 2-3 frases en español simple lo que ve el dueño "
          f"este mes {month} según estas tarjetas (sin inventar cifras, "
          f"solo conecta lo visible):\n{lineas}"}],
        model=model or s.OPENAI_FAST_MODEL)
    return r.content or ""


def compose(month: str, pool: list[dict], anchor_comments: dict,
            exposures: list[dict], ex, wid: str | None = None,
            design_fn=None, summary_fn=None,
            hoy: datetime | None = None) -> dict:
    """Ensambla el dashboard JSON. design_fn/summary_fn inyectables (tests)."""
    design_fn = design_fn or D.design
    summary_fn = summary_fn or weekly_summary
    wid = wid or week_id()

    try:
        tiene_datos = bool(ex("get_signals", {"month": month})
                           .get("signals", {}).get("tiene_datos"))
    except Exception:
        tiene_datos = True  # si no se puede saber, no bloquear por defecto
    ancs = anchors(month, ex, anchor_comments)

    reservadas = [c for c in D.reserved_cards(month, ex)
                  if c["component"] in ("receipts_resolution",
                                        "receivables_resolution")]
    criticas = [it for it in pool
                if it.get("severity") == "critical"
                and it.get("actionability") == "high"]
    # Orden: críticas accionables, receivables, receipts, warnings impacto.
    # Solo actionability high compite como acción; medium va a discovery
    # (si no, el pool de acciones devora todo y no queda nada que rotar).
    acciones_pool = criticas + sorted(
        [it for it in pool if it.get("severity") == "warning"
         and it.get("actionability") == "high"],
        key=lambda it: -_IMP.get(it.get("financial_impact"), 0))
    hay_problemas = bool(reservadas or criticas)
    # Regla obligatoria: si hay acciones pendientes, al menos 1 entra.
    # Tope total 3 acciones (reservadas + diseñadas): las deterministas
    # ya ocupan su lugar.
    n_acciones = min(max(0, 3 - len(reservadas)),
                     len(acciones_pool)) if hay_problemas else 0
    n_discovery = 4 if hay_problemas else 5
    elegidas_acc = acciones_pool[:n_acciones]
    # Lo accionable que no cupo compite en discovery (nada se pierde).
    resto = [it for it in pool if it not in elegidas_acc]
    elegidas_dis = discover(resto, exposures,
                            min(n_discovery, len(resto)), hoy, wid)

    componentes = [c for c in D.PROPS_SCHEMAS if c not in D.RESERVED]
    disenadas = []
    elegidas = elegidas_acc + elegidas_dis
    if elegidas:
        disenadas = design_fn(_para_disenar(elegidas),
                              componentes)["cards"]
        # Garantía 1:1: lo no cubierto (faltantes o ids duplicados) va a
        # un segundo intento solo con los ausentes.
        cubiertos: dict[str, int] = {}
        for c in disenadas:
            cubiertos[c["insight_id"]] = cubiertos.get(c["insight_id"], 0) + 1
        ausentes = [it for it in elegidas
                    if sum(1 for c in disenadas
                           if c["insight_id"] == (it.get("id") or it.get("kind"))) == 0]
        if ausentes:
            mas = design_fn(_para_disenar(ausentes),
                            componentes)["cards"]
            vistos = {c["insight_id"] for c in disenadas}
            disenadas.extend(c for c in mas
                             if c["insight_id"] not in vistos)
        # Garantía final sin LLM: tarjeta de texto con los datos validados
        # del propio insight (título/detalle/evidencia real, nada inventado).
        cubiertos = {c["insight_id"] for c in disenadas}
        for it in elegidas:
            iid = it.get("id") or it.get("kind")
            if iid not in cubiertos:
                ev = [f"{e.get('señal')}: {e.get('valor', '')} "
                      f"{e.get('unidad', '')}".strip()
                      for e in (it.get("evidencia") or [])]
                disenadas.append({
                    "insight_id": iid, "component": "insight_text",
                    "props": {"title": it.get("titulo", ""),
                              "body": it.get("detalle", ""),
                              "evidence": ev},
                    "rationale": "respaldo determinista: el diseño no cubrió "
                                 "este insight"})
                cubiertos.add(iid)

    ids_acc = {i.get("id") or i.get("kind") for i in elegidas_acc}
    cards_acc = [c for c in disenadas if c["insight_id"] in ids_acc]
    cards_dis = [c for c in disenadas if c["insight_id"] not in ids_acc]
    todas = reservadas + disenadas
    summary = summary_fn(todas, month) if todas else ""
    exps = ([{"kind": c["component"],
              "fingerprint": str(sorted(c.get("props", {}).items()))}
             for c in reservadas] +
            [{"kind": it.get("kind"),
              "fingerprint": fingerprint(it.get("kind"),
                                         it.get("evidencia", []))}
             for it in elegidas_acc + elegidas_dis])
    return {"month": month, "week_id": wid, "anchors": ancs,
            "actions": reservadas + cards_acc,
            "discovery": cards_dis,
            "summary": summary, "_exposures": exps,
            "huella": huella(pool, month),
            # Incompleta = el mes tiene datos pero no hubo de dónde diseñar
            # (pool vacío: el Analista aún no corre) o el diseño no cubrió
            # nada. El endpoint no la guarda: el próximo GET reintenta en
            # vez de congelar una semana degenerada.
            "incompleta": (not pool and tiene_datos)
                          or (bool(pool) and not disenadas)}
