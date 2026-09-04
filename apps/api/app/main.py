"""MiNorte API.

- GET /health (para docker compose + frontend)
- GET /api/summary (T1: calculado del seed CSV; el Financial Engine
  determinístico real llega en T4)
"""

from datetime import datetime
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
from app.integrations.sat import cfdi_xml as cx
from app.repositories import cfdi_repo, financial_repo as fr
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
    allow_origins=["http://localhost:3000"],
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


@app.get("/api/alerts")
def api_alerts(month: str | None = None):
    """Alertas accionables del Analista (T5). Lee tabla, fallback live."""
    company_id = get_current_company()
    month = month or _latest_month()
    sb = get_supabase()
    if sb is not None:
        try:
            got = fr.fetch_alerts(sb, company_id, month)
            if got:
                return {"month": month, "items": [_jalert(a) for a in got]}
        except Exception as e:
            print(f"[warn] alerts Supabase no disponible ({e}); live")
    return {"month": month, "items": [_jalert(a) for a in _alertas_live(month)]}


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
