"""MiNorte API.

- GET /health (para docker compose + frontend)
- GET /api/summary (T1: calculado del seed CSV; el Financial Engine
  determinístico real llega en T4)
"""

from collections import defaultdict
from datetime import datetime, timedelta
from decimal import Decimal
from functools import lru_cache
from pathlib import Path
from zoneinfo import ZoneInfo

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.db import get_supabase
from app.financial import alerts as analyst
from app.financial import engine as engine
from app.financial import reconcile as rc
from app.integrations.mail.provider import MailError, get_mail_provider
from app.operator import collections as op
from app.repositories import collections_repo as col
from app.repositories import financial_repo as fr
from app.routes.tickets import router as tickets_router
from app.schemas.cfdi import Cfdi
from app.schemas.financial import FinancialSummary
from app.schemas.transaction import Transaction

settings = get_settings()
MX_TZ = ZoneInfo(settings.TZ)

app = FastAPI(title=settings.APP_NAME, version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_origin_regex=r"^http://(?:10(?:\.\d{1,3}){3}|192\.168(?:\.\d{1,3}){2}|172\.(?:1[6-9]|2\d|3[01])(?:\.\d{1,3}){2}):3000$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(tickets_router)


def get_current_company() -> str:
    """Single-company demo. TODO(auth): reemplazar por Supabase Auth."""
    return settings.COMPANY_ID


@lru_cache
def _seed() -> list[Transaction]:
    """Delegado a app.data (fuente única API+MCP)."""
    from app import data as _data

    return _data.get_transactions()


@app.get("/health")
def health():
    return {"status": "ok", "company_id": get_current_company()}


@lru_cache
def _cfdis() -> list[Cfdi]:
    """CFDIs: delegado a app.data (T3)."""
    from app import data as _data

    return _data.get_cfdis()


@app.get("/api/cfdis")
def api_cfdis(tipo: str | None = None, limit: int = 50):
    """Lista CFDIs (T3). Filtra tipo=emitido|recibido. T5 los concilia."""
    items = _cfdis()
    if tipo in ("emitido", "recibido"):
        items = [c for c in items if c.tipo == tipo]
    total = len(items)
    return {"total": total, "items": [c.model_dump(mode="json") for c in items[: max(1, min(limit, 200))]]}


@lru_cache
def _live_matches():
    """Matches: delegado a app.data."""
    from app import data as _data

    return _data.get_matches()


def _latest_month() -> str:
    txns = _seed()
    ult = max(t.date for t in txns)
    return f"{ult.year}-{ult.month:02d}"


def _alertas_live(month: str) -> list[dict]:
    anio, mes = map(int, month.split("-"))
    txns, cfdis = _seed(), _cfdis()
    return analyst.generar_alertas(txns, cfdis, _live_matches(),
                                   anio, mes, get_current_company())


def _jalert(a: dict) -> dict:
    return {**a, "total": str(a["total"]) if a["total"] is not None else None}


def _solo_deterministas(items: list[dict]) -> list[dict]:
    """La tabla alerts es solo hechos; lo interpretativo vive en el Analista."""
    from app.financial.alerts import REGLAS

    return [a for a in items if a.get("rule") in REGLAS]


@app.get("/api/alerts")
def api_alerts(month: str | None = None):
    """Alertas deterministas accionables (T5). Lee tabla, fallback live."""
    company_id = get_current_company()
    month = month or _latest_month()
    sb = get_supabase()
    if sb is not None:
        try:
            got = fr.fetch_alerts(sb, company_id, month)
            if got:
                return {"month": month, "items": [_jalert(a) for a in _solo_deterministas(got)]}
        except Exception as e:
            print(f"[warn] alerts Supabase no disponible ({e}); live")
    return {"month": month, "items": [_jalert(a) for a in _alertas_live(month)]}


@app.get("/api/signals")
def api_signals(month: str | None = None):
    """Señales numéricas del motor para el Analista (fórmulas, sin juicio).

    Es lo que la IA recibirá en T8 junto con las alertas para decidir
    qué tarjetas mostrar en la UI generativa.
    """
    month = month or _latest_month()
    anio, mes = map(int, month.split("-"))
    s = engine.signals(_seed(), _cfdis(), _live_matches(), anio, mes)

    def _j(v):
        if isinstance(v, Decimal):
            return str(v)
        if isinstance(v, dict):
            return {k: _j(x) for k, x in v.items()}
        return v

    return {"month": month, "signals": {k: _j(v) for k, v in s.items()},
            "brief": engine.brief_mensual(s, anio, mes)}


@app.get("/api/metric")
def api_metric(name: str, month: str | None = None):
    """Una métrica por nombre (para el Diseñador y debug).

    Desconocida -> 400 con el catálogo (nunca null silencioso).
    """
    from fastapi import HTTPException

    from app.mcp import tools as T

    try:
        return T.get_metric(name, month)
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.get("/api/receivables")
def api_receivables():
    """Cuentas por cobrar abiertas (T5). Tabla primero, live si no hay."""
    company_id = get_current_company()
    sb = get_supabase()
    if sb is not None:
        try:
            got = fr.fetch_receivables(sb, company_id)
            if got:
                return {"total": len(got), "total_pending": str(sum(
                    (Decimal(r["amount_pending"]) for r in got), Decimal("0"))),
                    "items": got}
        except Exception as e:
            print(f"[warn] receivables Supabase no disponible ({e}); live")
    txns, cfdis = _seed(), _cfdis()
    recs = rc.detectar_cxc(cfdis, rc.conciliar(txns, cfdis), company_id)
    items = [r.model_dump(mode="json") for r in recs]
    return {"total": len(items),
            "total_pending": str(sum((r.amount_pending for r in recs), Decimal("0"))),
            "items": items}


@app.get("/api/matches")
def api_matches(status: str | None = None, limit: int = 50):
    """Debug de conciliación (T5): score por movimiento."""
    todos = _live_matches()
    counts = {"auto": 0, "review": 0, "unmatched": 0}
    for m in todos:
        counts[m.status] += 1
    items = [m for m in todos if status is None or m.status == status]
    return {"counts": counts,
            "items": [m.model_dump(mode="json") for m in items[: max(1, min(limit, 200))]]}


@app.get("/api/summary", response_model=FinancialSummary)
def api_summary():
    """Resumen del ÚLTIMO mes con totales bancarios (coherente con el
    dashboard del spec). Lee snapshot si existe, si no calcula live.

    Nota T4: esta cuenta es pagadora y se fondea desde BBVA; el motor
    (engine.operativos) separa flujo operativo vs interno para el
    Consultor. Impuesto/CxC/sin-CFDI se refinan en T4/T5.
    """
    company_id = get_current_company()
    sb = get_supabase()
    if sb is not None:
        try:
            month = fr.fetch_latest_month(sb, company_id)
            snap = fr.fetch_snapshot(sb, company_id, month) if month else None
            if snap:
                return FinancialSummary(
                    company_id=company_id, ventas=snap["ventas"],
                    gastos=snap["gastos"], utilidad=snap["utilidad"],
                    efectivo=snap["efectivo"],
                    impuesto_estimado=snap["impuesto_estimado"],
                    cuentas_por_cobrar=snap["cxc_total"],
                    gastos_sin_cfdi_count=snap.get("sin_cfdi_count", 0),
                    gastos_sin_cfdi_total=snap.get("sin_cfdi_total", 0),
                    updated_at=datetime.now(MX_TZ),
                )
        except Exception as e:
            print(f"[warn] snapshot no disponible ({e}); calculo live")
    txns = _seed()
    ultimo = max(t.date for t in txns)
    mes = [t for t in txns if (t.date.year, t.date.month) == (ultimo.year, ultimo.month)]
    ventas = sum((t.amount for t in mes if t.type == "ingreso" and not t.es_interno), Decimal("0"))
    gastos = sum((t.amount for t in mes if t.type == "egreso" and not t.es_interno), Decimal("0"))
    utilidad = ventas - gastos
    ordenados = sorted(txns, key=lambda t: (t.date, t.id))
    efectivo = ordenados[-1].balance or Decimal("0")
    matches = _live_matches()
    recs = rc.detectar_cxc(_cfdis(), matches, company_id)
    sin = [m for m in matches if m.status == "unmatched"
           and (t := next((x for x in txns if x.id == m.transaction_id), None))
           and t.type == "egreso"]
    sin_total = sum((next(x for x in txns if x.id == m.transaction_id).amount
                     for m in sin), Decimal("0"))
    return FinancialSummary(
        company_id=get_current_company(),
        ventas=ventas,
        gastos=gastos,
        utilidad=utilidad,
        efectivo=efectivo,
        impuesto_estimado=round(utilidad * Decimal("0.30")) if utilidad > 0 else Decimal("0"),
        cuentas_por_cobrar=sum((r.amount_pending for r in recs), Decimal("0")),
        gastos_sin_cfdi_count=len(sin),
        gastos_sin_cfdi_total=sin_total,
        updated_at=datetime.now(MX_TZ),
    )


@app.get("/api/dashboard")
def api_dashboard():
    """Contrato agregado para el dashboard MiNorte.

    Todos los importes y series salen del mismo source of truth que el motor:
    Supabase cuando está configurado y poblado; seed bancario como fallback.
    La UI no calcula contabilidad ni contiene cifras de demostración quemadas.
    """
    txns = _seed()
    cfdis = _cfdis()
    matches = _live_matches()
    latest = max(t.date for t in txns)
    latest_month = f"{latest.year}-{latest.month:02d}"
    current = [t for t in txns if (t.date.year, t.date.month) == (latest.year, latest.month)]

    month_keys = sorted({(t.date.year, t.date.month) for t in txns})[-6:]
    monthly = []
    for year, month in month_keys:
        sales, expenses, margin = engine.banco_mes(txns, year, month)
        monthly.append({
            "month": f"{year}-{month:02d}",
            "sales": sales,
            "expenses": expenses,
            "profit": sales - expenses,
            "margin": margin,
            "cash": engine.efectivo_a_fin_de_mes(txns, year, month),
        })

    by_day: dict[str, dict] = {}
    for t in current:
        key = t.date.date().isoformat()
        row = by_day.setdefault(key, {
            "date": key, "income": Decimal("0"), "expenses": Decimal("0"),
            "balance": None, "count": 0,
        })
        row["income" if t.type == "ingreso" else "expenses"] += t.amount
        if t.balance is not None:
            row["balance"] = t.balance
        row["count"] += 1
    daily = [by_day[key] for key in sorted(by_day)]

    expense_groups: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
    customer_groups: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
    for t in current:
        if t.type == "egreso" and not t.es_interno:
            expense_groups[t.rubro or t.categoria or "por_clasificar"] += t.amount
        if t.type == "ingreso" and not t.es_interno:
            customer_groups[t.merchant_name or "Cliente"] += t.amount

    total_expenses = sum(expense_groups.values(), Decimal("0"))
    total_customers = sum(customer_groups.values(), Decimal("0"))
    categories = [{
        "name": name, "amount": amount,
        "percent": (amount / total_expenses) if total_expenses else Decimal("0"),
    } for name, amount in sorted(expense_groups.items(), key=lambda item: item[1], reverse=True)]
    customers = [{
        "name": name, "amount": amount,
        "percent": (amount / total_customers) if total_customers else Decimal("0"),
    } for name, amount in sorted(customer_groups.items(), key=lambda item: item[1], reverse=True)]

    start_activity = latest.date() - timedelta(days=34)
    activity_counts: dict[str, int] = defaultdict(int)
    for t in txns:
        if start_activity <= t.date.date() <= latest.date():
            activity_counts[t.date.date().isoformat()] += 1
    activity = []
    for offset in range(35):
        day = start_activity + timedelta(days=offset)
        activity.append({"date": day.isoformat(), "count": activity_counts[day.isoformat()]})

    recent = [{
        "id": t.id,
        "date": t.date.isoformat(),
        "description": t.description,
        "merchant": t.merchant_name,
        "amount": t.amount,
        "type": t.type,
        "category": t.rubro or t.categoria,
    } for t in sorted(txns, key=lambda item: (item.date, item.id), reverse=True)[:6]]

    match_counts = {"auto": 0, "review": 0, "unmatched": 0}
    for match in matches:
        match_counts[match.status] += 1

    summary = api_summary().model_dump(mode="json")
    receivables = api_receivables()
    alerts = api_alerts(latest_month)
    signal_values = engine.signals(txns, cfdis, matches, latest.year, latest.month)

    def _json(value):
        if isinstance(value, Decimal):
            return str(value)
        if isinstance(value, dict):
            return {key: _json(item) for key, item in value.items()}
        if isinstance(value, list):
            return [_json(item) for item in value]
        return value

    return _json({
        "month": latest_month,
        "updated_at": datetime.now(MX_TZ).isoformat(),
        "summary": summary,
        "signals": signal_values,
        "alerts": alerts["items"],
        "receivables": receivables,
        "matches": {"counts": match_counts},
        "monthly": monthly,
        "daily": daily,
        "categories": categories,
        "customers": customers,
        "recent_transactions": recent,
        "activity": activity,
        "cfdis": {
            "issued": sum(1 for c in cfdis if c.tipo == "emitido"),
            "received": sum(1 for c in cfdis if c.tipo == "recibido"),
        },
    })


# ==================== Cobranza (T9) ====================

def _sb_or_503():
    sb = get_supabase()
    if sb is None:
        from fastapi import HTTPException
        raise HTTPException(503, "sin Supabase: configura SUPABASE_URL/KEY en .env")
    return sb


def _company_row(sb, company_id: str) -> dict:
    try:
        res = (sb.table("companies").select("*").eq("id", company_id).execute())
        if res.data:
            return res.data[0]
    except Exception:
        pass
    import json as _json
    for base in (Path.cwd(), Path(__file__).resolve().parents[3]):
        p = base / "seed" / "company.json"
        if p.exists():
            c = _json.loads(p.read_text())
            return {"razon_social": c["razon_social"],
                    "nombre_comercial": c.get("nombre_comercial", "")}
    return {"razon_social": company_id, "nombre_comercial": ""}


def _cobranza_items(sb, company_id: str, ids: list[str] | None = None):
    """(recs_json, cfdis_by_uuid, contacts_list, company)."""
    try:
        recs = fr.fetch_receivables(sb, company_id)
    except Exception as e:
        from fastapi import HTTPException
        raise HTTPException(503, f"corre migrations/004_collections.sql ({e})")
    if ids:
        recs = [r for r in recs if r["id"] in ids]
    uuids = {r["cfdi_id"] for r in recs}
    cfdis = {c.uuid: c for c in _cfdis() if c.uuid in uuids}
    contacts = col.list_contacts(sb, company_id)
    return recs, cfdis, contacts, _company_row(sb, company_id)


@app.get("/api/collections/draft")
def api_collections_draft(ids: str | None = None):
    """Borradores sin enviar nada. ids=A,B para subconjunto (envío parcial)."""
    sb = _sb_or_503()
    company_id = get_current_company()
    wanted = ids.split(",") if ids else None
    recs, cfdis, contacts, company = _cobranza_items(sb, company_id, wanted)
    out = []
    for r in recs:
        c = cfdis.get(r["cfdi_id"])
        if c is None:
            continue
        out.append(op.prepare_draft(
            r, c.model_dump(mode="json"),
            col.resolve(contacts, r["customer_rfc"], r.get("customer_name", "")),
            company))
    return {"items": out}


@app.get("/api/collections/contacts")
def api_collections_contacts():
    """Directorio + cobertura: qué CxC abiertas tienen correo."""
    sb = _sb_or_503()
    company_id = get_current_company()
    recs, _, contacts, _ = _cobranza_items(sb, company_id)
    return {"contacts": contacts,
            "cobertura": [
                {"receivable_id": r["id"], "customer_rfc": r["customer_rfc"],
                 "customer_name": r.get("customer_name", ""),
                 "tiene_email": bool((col.resolve(
                     contacts, r["customer_rfc"], r.get("customer_name", "")) or {}).get("email"))}
                for r in recs]}


@app.post("/api/collections/contacts")
def api_collections_contacts_upsert(body: dict):
    """Alta/manual del directorio: guarda email y habilita el envío."""
    sb = _sb_or_503()
    company_id = get_current_company()
    try:
        row = col.upsert_contact(
            sb, company_id, body.get("customer_rfc", ""),
            body.get("email", ""), body.get("customer_name", ""),
            body.get("phone", ""))
    except ValueError as e:
        from fastapi import HTTPException
        raise HTTPException(400, str(e))
    except Exception as e:
        from fastapi import HTTPException
        raise HTTPException(503, f"corre migrations/004_collections.sql ({e})")
    return row


@app.post("/api/collections/send")
def api_collections_send(body: dict):
    """Envía recordatorios. Parcial por diseño: lo bloqueado no frena el lote.

    body: {receivable_ids?: [...], confirm: bool, force?: bool}
    Sin confirm=true devuelve 400 con los borradores (revisar antes).
    """
    from fastapi import HTTPException

    sb = _sb_or_503()
    company_id = get_current_company()
    if not body.get("confirm"):
        recs, cfdis, contacts, company = _cobranza_items(
            sb, company_id, body.get("receivable_ids"))
        drafts = [op.prepare_draft(
            r, cfdis[r["cfdi_id"]].model_dump(mode="json"),
            col.resolve(contacts, r["customer_rfc"], r.get("customer_name", "")),
            company)
            for r in recs if r["cfdi_id"] in cfdis]
        raise HTTPException(400, {"error": "confirm requerido", "drafts": drafts})
    try:
        provider = get_mail_provider()
    except MailError as e:
        raise HTTPException(503, str(e))
    recs, cfdis, contacts, company = _cobranza_items(
        sb, company_id, body.get("receivable_ids"))
    drafts = [op.prepare_draft(
        r, cfdis[r["cfdi_id"]].model_dump(mode="json"),
        col.resolve(contacts, r["customer_rfc"], r.get("customer_name", "")),
        company)
        for r in recs if r["cfdi_id"] in cfdis]
    force = bool(body.get("force"))
    items = op.send_batch(
        drafts, provider,
        lambda rid: col.enviado_reciente(sb, company_id, rid),
        lambda it: col.record_action(sb, company_id, it),
        force=force)
    resumen = {"enviada": 0, "bloqueada_falta_email": 0, "omitida_24h": 0, "fallida": 0}
    for it in items:
        resumen[it["status"]] = resumen.get(it["status"], 0) + 1
    return {"provider": provider.name, "resumen": resumen, "items": items}


# ==================== Consultor + créditos (T8) ====================

@app.post("/api/chat")
def api_chat(body: dict):
    """Pregúntame sobre tu negocio (Consultor: interpreta, no calcula)."""
    from fastapi import HTTPException

    from app.agents import consultant
    from app.agents.llm import LLMError
    from app.repositories import chat_repo

    texto = (body.get("mensaje") or "").strip()
    if not texto:
        raise HTTPException(400, "mensaje vacío")
    sb = _sb_or_503()
    company_id = get_current_company()
    cid = body.get("conversation_id")
    try:
        if cid:
            if not chat_repo.get_conversacion(sb, company_id, cid):
                raise HTTPException(404, "conversación no existe")
        else:
            cid = chat_repo.nueva_conversacion(sb, company_id)["id"]
        historial = chat_repo.historial(sb, cid)
        chat_repo.guardar_turno(sb, cid, "usuario", texto)
        try:
            from app.repositories import profile_repo
            try:
                perfil = profile_repo.get_profile(sb, company_id)
            except Exception:
                perfil = None
            r = consultant.ask(texto, historial, perfil=perfil)
        except LLMError as e:
            raise HTTPException(502, f"modelo no disponible: {e}")
        chat_repo.guardar_turno(sb, cid, "asistente", r["respuesta"],
                                r.get("llamadas", [{"tool": t} for t in r["tools_usados"]]),
                                r.get("tarjetas", []))
        return {"conversation_id": cid, "respuesta": r["respuesta"],
                "tools_usados": r["tools_usados"],
                "llamadas": r.get("llamadas", []),
                "tarjetas": r.get("tarjetas", []),
                "truncado": r["truncado"]}
    except HTTPException:
        raise
    except Exception as e:
        if ("PGRST205" in str(e) or "PGRST204" in str(e)
            or "Could not find the table" in str(e)
            or "Could not find the 'family' column" in str(e)):
            if "'tarjetas'" in str(e):
                raise HTTPException(
                    503, f"corre migrations/013_consultant_ui.sql ({e})")
            raise HTTPException(503, f"corre migrations/006_agents.sql ({e})")
        raise


@app.post("/api/analyst/run")
def api_analyst_run(body: dict | None = None):
    """Analista: señales del mes → insights rankeados con evidencia.

    Idempotente: reemplaza los insights del mes (igual que alertas).
    """
    from fastapi import HTTPException

    from app.agents import analyst as _an
    from app.agents.llm import LLMError
    from app.repositories import analyst_repo as _ar
    from app.repositories import profile_repo as _pr

    sb = _sb_or_503()
    company_id = get_current_company()
    month = (body or {}).get("month") or _latest_month()
    try:
        try:
            perfil = _pr.get_profile(sb, company_id)
        except Exception:
            perfil = None
        try:
            r = _an.run(month, perfil=perfil, company_id=company_id)
        except LLMError as e:
            raise HTTPException(502, f"modelo no disponible: {e}")
        except ValueError as e:
            # Validación determinista rechazó insights: JSON con motivos,
            # nunca 500 plano (el pipe con json.tool no debe tronar).
            raise HTTPException(422, {"error": "insights inválidos",
                                      "detalle": str(e)})
        try:
            guardados = _ar.reemplazar(sb, company_id, month, r["insights"])
        except Exception as e:
            if ("PGRST205" in str(e) or "PGRST204" in str(e)
                    or "Could not find the table" in str(e)
                    or "Could not find the 'family' column" in str(e)
                    or "Could not find the 'actionability' column" in str(e)):
                raise HTTPException(
                    503, "corre migrations/010_analyst_insights.sql y "
                         f"012_analyst_scoring.sql ({e})")
            raise
        try:
            anchors = _ar.guardar_anchors(sb, company_id, month,
                                          r.get("anchor_analysis", []))
        except Exception as e:
            if ("PGRST205" in str(e) or "PGRST204" in str(e)
            or "Could not find the table" in str(e)
            or "Could not find the 'family' column" in str(e)):
                raise HTTPException(
                    503, f"corre migrations/012_analyst_scoring.sql ({e})")
            raise
        return {"month": month, "insights": guardados,
                "anchor_analysis": anchors,
                "tools_usados": r["tools_usados"],
                "truncado": r["truncado"]}
    except HTTPException:
        raise


@app.get("/api/analyst/insights")
def api_analyst_insights(month: str | None = None):
    """Insights guardados del mes (lectura para UI y Diseñador)."""
    from fastapi import HTTPException

    from app.repositories import analyst_repo as _ar

    sb = _sb_or_503()
    company_id = get_current_company()
    month = month or _latest_month()
    try:
        return {"month": month,
                "insights": _ar.listar(sb, company_id, month)}
    except Exception as e:
        if ("PGRST205" in str(e) or "PGRST204" in str(e)
            or "Could not find the table" in str(e)
            or "Could not find the 'family' column" in str(e)):
            raise HTTPException(
                503, f"corre migrations/010_analyst_insights.sql ({e})")
        raise


@app.get("/api/dashboard/gen")
def api_dashboard_gen(month: str | None = None, week: str | None = None):
    """Dashboard generativo JSON (sin frontend aún, listo para DynamicUI).

    4 anchors + acciones condicionales + discovery rotativo + summary.
    Idempotente por semana ISO: si ya existe, la devuelve sin regenerar
    (sin gastar LLM).
    """
    from fastapi import HTTPException

    from app import composition as _cp
    from app.agents.llm import LLMError
    from app.mcp import tools as _T
    from app.repositories import analyst_repo as _ar
    from app.repositories import composition_repo as _cr

    sb = _sb_or_503()
    company_id = get_current_company()
    month = month or _latest_month()
    wid = week or _cp.week_id()
    try:
        cached = _cr.leer_composicion(sb, company_id, wid)
    except Exception:
        cached = None
    if cached:
        return cached
    try:
        pool = _ar.listar(sb, company_id, month)
        comments = {a["metric"]: a["comment"]
                    for a in _ar.listar_anchors(sb, company_id, month)}
        exposures = _cr.historial(sb, company_id)
        try:
            out = _cp.compose(month, pool, comments, exposures, _T.execute,
                              wid)
        except LLMError as e:
            raise HTTPException(502, f"modelo no disponible: {e}")
        exps = out.pop("_exposures")
        try:
            _cr.guardar_composicion(sb, company_id, wid, month, out)
            _cr.registrar(sb, company_id, wid, exps)
        except Exception as e:
            if ("PGRST205" in str(e) or "PGRST204" in str(e)
            or "Could not find the table" in str(e)
            or "Could not find the 'family' column" in str(e)):
                raise HTTPException(
                    503, "corre migrations/011_insight_exposures.sql y "
                         "012_analyst_scoring.sql "
                    f"({e})")
            raise
        return out
    except HTTPException:
        raise


@app.get("/api/critical-bar")
def api_critical_bar(month: str | None = None):
    """Barra compacta de pendientes (lectura, sin LLM).

    Siempre visible sobre cualquier modo: reservadas deterministas +
    conteo de críticos vigentes. Cuesta ms.
    """
    from app.agents import designer as _D
    from app.mcp import tools as _T

    company_id = get_current_company()
    month = month or _latest_month()
    # Solo lo accionable cuenta como pendiente: tax_summary es informativo.
    reservadas = [c for c in _D.reserved_cards(month, _T.execute)
                  if c["component"] in ("receipts_resolution",
                                        "receivables_resolution")]
    criticos = [c for c in reservadas]
    try:
        sig = _T.get_signals(month).get("signals", {})
        if (sig.get("runway_dias") is not None
                and sig["runway_dias"] <= 7):
            criticos.append({"insight_id": f"{month}_caja",
                             "component": "insight_text",
                             "props": {"title": "Caja crítica",
                                       "body": f"{sig['runway_dias']} días de caja.",
                                       "tone": "urgent"},
                             "rationale": "determinista: runway<=7"})
    except Exception:
        pass
    return {"month": month, "pendientes": len(criticos),
            "items": criticos}


@app.get("/api/drill")
def api_drill(insight_id: str, month: str | None = None):
    """Deep-dive v1 determinista: evidencia del insight + drill.

    Resuelve el insight guardado, corre Nivel 0/1/2 (merchants) y devuelve
    tarjetas deterministas + texto del Consultor interpretando (1 llamada
    barata sin tools: todo el contexto viaja en el prompt).
    """
    from fastapi import HTTPException

    from app.agents import llm as _llm
    from app.config import get_settings as _gs
    from app.mcp import tools as _T
    from app.repositories import analyst_repo as _ar

    sb = _sb_or_503()
    company_id = get_current_company()
    month = month or _latest_month()
    insights = _ar.listar(sb, company_id, month)
    ins = next((i for i in insights if i.get("id") == insight_id), None)
    if not ins:
        raise HTTPException(404, "insight no existe en ese mes")
    tarjetas: list[dict] = []
    contexto = [f"Insight: {ins.get('titulo')} — {ins.get('detalle')}"]
    for e in (ins.get("evidencia") or [])[:4]:
        contexto.append(f"- {e.get('señal')} = {e.get('valor')} "
                        f"{e.get('unidad', '')}")
    # Drill determinista por rubro si la evidencia lo sugiere
    try:
        merchants = _T.get_merchants(limit=5, month=month)
        if merchants:
            top = merchants[:4]
            tarjetas.append({
                "insight_id": f"{insight_id}_drill", "component": "bars_total",
                "props": {"title": "Top comercios relacionados",
                          "total": str(sum(float(str(m.get('total', 0)))
                                           for m in top)),
                          "values": [float(str(m.get("total", 0)))
                                     for m in top],
                          "labels": [str(m.get("nombre", "?"))[:12]
                                     for m in top],
                          "footnote": "Desglose determinista del rubro."},
                "rationale": "determinista: drill Nivel 1"})
            contexto.append("Top comercios: " + ", ".join(
                f"{m.get('nombre')} ({m.get('total')})" for m in top))
    except Exception:
        pass
    try:
        r = _llm.chat(
            [{"role": "user", "content":
              "Explica en 2-3 frases en español simple, para un dueño que "
              "no sabe de finanzas, este hallazgo y qué hacer. Sin cifras "
              "nuevas, solo conecta lo visible:\n" + "\n".join(contexto)}],
            model=_gs().OPENAI_FAST_MODEL)
        texto = r.content or ""
    except _llm.LLMError as e:
        raise HTTPException(502, f"modelo no disponible: {e}")
    return {"insight_id": insight_id, "month": month, "texto": texto,
            "tarjetas": tarjetas}


@app.get("/api/scenarios")
def api_scenarios_list():
    """Escenarios guardados (origen propio, separados de insights)."""
    from app.repositories import scenario_repo as _sr

    sb = _sb_or_503()
    return {"items": _sr.listar(sb, get_current_company())}


@app.post("/api/scenarios")
def api_scenarios_save(body: dict):
    """Guarda una simulación como escenario persistente."""
    from fastapi import HTTPException

    from app.repositories import scenario_repo as _sr

    sb = _sb_or_503()
    company_id = get_current_company()
    try:
        row = _sr.guardar(sb, company_id, body.get("conversation_id"),
                          body.get("titulo", ""), body.get("detalle", ""),
                          body.get("cifras", {}))
        return row
    except Exception as e:
        if "PGRST205" in str(e) or "Could not find the table" in str(e):
            raise HTTPException(
                503, f"corre migrations/013_consultant_ui.sql ({e})")
        raise


@app.post("/api/loans/apply")
def api_loans_apply(body: dict):
    """Contratación MOCK de crédito del catálogo (spec #10).

    Sin confirm=true devuelve 400 con términos para revisar.
    Con confirm registra la solicitud (folio) — producción enchufaría Banorte.
    """
    from decimal import Decimal as _D

    from fastapi import HTTPException

    from app.financial import engine as _en
    from app.mcp import tools as _T

    company_id = get_current_company()
    try:
        opciones = _T.banorte_get_credit_options()["items"]
    except Exception as e:
        raise HTTPException(503, str(e))
    op = next((o for o in opciones if o["id"] == body.get("option_id")), None)
    if not op:
        raise HTTPException(400, {"error": "option_id inválido",
                                  "opciones": [o["id"] for o in opciones]})
    try:
        monto = _D(str(body.get("amount", "")))
    except Exception:
        raise HTTPException(400, "amount inválido")
    meses = body.get("months")
    if meses is None:
        meses = min(op["plazos_meses"])
    if int(meses) not in op["plazos_meses"]:
        raise HTTPException(400, {"error": "plazo no ofrecido",
                                  "plazos": op["plazos_meses"]})
    if not (_D(op["monto_min"]) <= monto <= _D(op["monto_max"])):
        raise HTTPException(400, {"error": "monto fuera de rango",
                                  "rango": [op["monto_min"], op["monto_max"]]})
    txns = _seed()
    a, m = map(int, _latest_month().split("-"))
    fm = [t for t in txns if (t.date.year, t.date.month) == (a, m)]
    util = sum((t.amount for t in fm if t.type == "ingreso" and not t.es_interno), _D("0")) - sum(
        (t.amount for t in fm if t.type == "egreso" and not t.es_interno), _D("0"))
    pago = _en.amortizar_francesa(monto, _D(op["tasa_anual"]) / 12, int(meses))
    total_intereses = pago * int(meses) - monto
    cobertura = (util / pago) if pago > 0 else None
    veredicto = ("no_viable" if cobertura is None or cobertura < 1
                 else "ajustada" if cobertura < _D("1.5") else "viable")
    comision = (monto * _D(op.get("comision_apertura_pct", "0"))).quantize(_D("0.01"))
    terms = {"option_id": op["id"], "nombre": op["nombre"],
             "amount": str(monto), "plazo_meses": int(meses),
             "tasa_anual": str(op["tasa_anual"]),
             "pago_mensual": str(pago),
             "costo_total": str(total_intereses + comision),
             "cobertura": (str(cobertura)
                           if cobertura is not None else None),
             "veredicto": veredicto, "mock": True}
    if not body.get("confirm"):
        raise HTTPException(400, {"error": "confirm requerido", "terms": terms})
    from app.repositories import chat_repo

    sb = _sb_or_503()
    try:
        return chat_repo.registrar_solicitud(sb, company_id, terms)
    except Exception as e:
        raise HTTPException(503, f"corre migrations/006_agents.sql ({e})")


# ==================== Perfil del negocio (T8) ====================

@app.get("/api/company/profile")
def api_company_profile():
    """Perfil + bandera configurado (para /ajustes)."""
    from app.repositories import profile_repo

    sb = _sb_or_503()
    company_id = get_current_company()
    try:
        row = profile_repo.get_profile(sb, company_id)
    except Exception as e:
        from fastapi import HTTPException
        raise HTTPException(503, f"corre migrations/007_business_profiles.sql ({e})")
    return {"configurado": row is not None, "perfil": row}


@app.put("/api/company/profile")
def api_company_profile_put(body: dict):
    """Alta/edición manual del perfil (nunca lo pisa el seed)."""
    from fastapi import HTTPException

    from app.repositories import profile_repo

    sb = _sb_or_503()
    try:
        return profile_repo.upsert_profile(sb, get_current_company(), body)
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        raise HTTPException(503, f"corre migrations/007_business_profiles.sql ({e})")


@app.get("/api/company/profile/sugerencia")
def api_company_profile_sugerencia():
    """Propuesta determinista desde datos (el dueño confirma en /ajustes)."""
    from app.repositories import profile_repo

    return profile_repo.sugerir_perfil(_seed(), _cfdis())
