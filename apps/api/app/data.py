"""Acceso a datos con degradación elegante (T8): Supabase primero, seed local.

Fuente única para la API y las tools MCP. Cacheado por proceso.
"""

from functools import lru_cache
from pathlib import Path

from app.config import get_settings
from app.db import get_supabase
from app.schemas.cfdi import Cfdi
from app.schemas.match import Match
from app.schemas.transaction import Transaction


def _seed_dir() -> Path:
    for base in (Path.cwd(), Path(__file__).resolve().parents[2]):
        if (base / "seed" / "transactions.csv").exists():
            return base / "seed"
    return Path.cwd() / "seed"


@lru_cache
def get_transactions() -> list[Transaction]:
    from app.integrations.banking.banorte_csv import cargar_csv
    from app.repositories import transactions_repo as repo

    company_id = get_settings().COMPANY_ID
    sb = get_supabase()
    if sb is not None:
        try:
            got = repo.fetch_ordered(sb, company_id)
            if got:
                return got
        except Exception as e:
            print(f"[warn] txns Supabase no disponible ({e}); uso CSV")
    return cargar_csv(_seed_dir() / "transactions.csv", company_id=company_id)


@lru_cache
def get_cfdis() -> list[Cfdi]:
    from app.integrations.sat import cfdi_xml as cx
    from app.repositories import cfdi_repo

    company_id = get_settings().COMPANY_ID
    sb = get_supabase()
    if sb is not None:
        try:
            got = cfdi_repo.fetch_all(sb, company_id)
            if got:
                return got
        except Exception as e:
            print(f"[warn] cfdis Supabase no disponible ({e}); uso XMLs")
    d = _seed_dir() / "cfdis"
    rfc = "CNM160812AB1"
    try:
        with open(_seed_dir() / "company.json", encoding="utf-8") as f:
            import json
            rfc = json.load(f).get("rfc", rfc)
    except Exception:
        pass
    xmls = sorted(d.rglob("*.xml")) if d.exists() else []
    return [cx.parsear_archivo(p, company_id, rfc, base=d) for p in xmls]


@lru_cache
def get_matches() -> list[Match]:
    from app.financial import reconcile as rc

    return rc.conciliar(get_transactions(), get_cfdis())


def latest_month() -> str:
    ult = max(t.date for t in get_transactions())
    return f"{ult.year}-{ult.month:02d}"
