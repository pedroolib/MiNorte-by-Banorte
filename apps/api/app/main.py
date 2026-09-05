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
from app.integrations.banking.banorte_csv import cargar_csv
from app.integrations.mail.provider import MailError, get_mail_provider
from app.integrations.sat import cfdi_xml as cx
from app.operator import collections as op
from app.repositories import cfdi_repo, collections_repo as col
from app.repositories import financial_repo as fr
from app.repositories import transactions_repo as repo
from app.schemas.cfdi import Cfdi
from app.schemas.financial import FinancialSummary
from app.schemas.transaction import Transaction

settings = get_settings()
MX_TZ = ZoneInfo(settings.TZ)


def _seed_path() -> Path:
    # local: <repo>/seed · docker: /app/seed (ver docker-compose.yml)
    candidatos = [Path.cwd() / "seed" / "transactions.csv"]
    f = Path(__file__).resolve()
    if len(f.parents) > 3:
        candidatos.append(f.parents[3] / "seed" / "transactions.csv")
    for p in candidatos:
        if p.exists():
            return p
    return candidatos[0]


SEED_CSV = _seed_path()
SEED_CFDI_DIR = SEED_CSV.parent / "cfdis"

app = FastAPI(title=settings.APP_NAME, version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def get_current_company() -> str:
    """Single-company demo. TODO(auth): reemplazar por Supabase Auth."""
    return settings.COMPANY_ID


@lru_cache
def _seed() -> list[Transaction]:
    company_id = get_settings().COMPANY_ID
    sb = get_supabase()
    if sb is not None:
        try:
            got = repo.fetch_ordered(sb, company_id)
            if got:
                return got
        except Exception as e:  # sin tablas/red: degradar a CSV
            print(f"[warn] Supabase no disponible ({e}); uso seed CSV local")
    return cargar_csv(SEED_CSV, company_id=company_id)


@app.get("/health")
def health():
    return {"status": "ok", "company_id": get_current_company()}


@lru_cache
def _cfdis() -> list[Cfdi]:
    """CFDIs: Supabase primero, XMLs del seed como fallback (T3)."""
    from app.repositories import cfdi_repo

    company_id = get_settings().COMPANY_ID
    sb = get_supabase()
    if sb is not None:
        try:
            got = cfdi_repo.fetch_all(sb, company_id)
            if got:
                return got
        except Exception as e:
            print(f"[warn] cfdis Supabase no disponible ({e}); uso XMLs locales")
    xmls = sorted(SEED_CFDI_DIR.rglob("*.xml")) if SEED_CFDI_DIR.exists() else []
    return [
        cx.parsear_archivo(p, company_id, "CNM160812AB1", base=SEED_CFDI_DIR)
        for p in xmls
    ]


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
    """Matches calculados al vuelo y cacheados (rápido en el seed)."""
    return rc.conciliar(_seed(), _cfdis())


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

    return {"month": month, "signals": {k: _j(v) for k, v in s.items()}}


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
    ventas = sum((t.amount for t in mes if t.type == "ingreso"), Decimal("0"))
    gastos = sum((t.amount for t in mes if t.type == "egreso"), Decimal("0"))
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
    """(recs_json, cfdis_by_uuid, contacts_by_rfc, company)."""
    try:
        recs = fr.fetch_receivables(sb, company_id)
    except Exception as e:
        from fastapi import HTTPException
        raise HTTPException(503, f"corre migrations/004_collections.sql ({e})")
    if ids:
        recs = [r for r in recs if r["id"] in ids]
    uuids = {r["cfdi_id"] for r in recs}
    cfdis = {c.uuid: c for c in _cfdis() if c.uuid in uuids}
    contacts = {c["customer_rfc"]: c for c in col.list_contacts(sb, company_id)}
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
            contacts.get(r["customer_rfc"]), company))
    return {"items": out}


@app.get("/api/collections/contacts")
def api_collections_contacts():
    """Directorio + cobertura: qué CxC abiertas tienen correo."""
    sb = _sb_or_503()
    company_id = get_current_company()
    recs, _, contacts, _ = _cobranza_items(sb, company_id)
    return {"contacts": list(contacts.values()),
            "cobertura": [
                {"receivable_id": r["id"], "customer_rfc": r["customer_rfc"],
                 "tiene_email": bool((contacts.get(r["customer_rfc"]) or {}).get("email"))}
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
            contacts.get(r["customer_rfc"]), company)
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
        contacts.get(r["customer_rfc"]), company)
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
