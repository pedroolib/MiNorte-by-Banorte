"""Operador tickets (spec #3.3 caso 1): ticket real -> match -> factura real.

Flujo por ticket (independiente del resto del sistema):
  extracción (Vision, `integrations/invoicing/vision.py`)
  -> candidatos de match (misma fórmula que `financial/reconcile.py`,
     nunca se reimplementa el score)
  -> perfil fiscal (`seed/company.json` / `business_profiles`)
  -> payload real para el browser agent (`browser/agent.py`)
  -> confirmación humana antes de la acción irreversible (spec #19)
  -> CFDI real -> reconciliación (`reconcile_cfdi`).

No calcula ni concilia: reutiliza `reconcile.amount_score/date_score/
merchant_score` tal cual (principio #9, no tocar el motor).
"""

from __future__ import annotations

import json
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from app.financial import reconcile as rc
from app.schemas.transaction import Transaction


# SAT "público en general" (real, universal): el RFC/régimen/uso_cfdi
# que cualquier portal de facturación mexicano real acepta para un
# consumidor final, sin necesitar un RFC de negocio registrado de verdad.
# Para el demo: la empresa ficticia del seed (CNM160812AB1) no existe en
# el SAT real, así que un portal real la rechaza (correctamente) — esto
# permite completar el flujo real hasta un CFDI real y verificable.
#
# razon_social: "CLIENTE GENERICO", NO "PUBLICO EN GENERAL" — Wansoft
# (portal real probado) rechaza esa segunda frase explícitamente y
# sugiere "CLIENTE GENERICO" como valor válido para el RFC genérico. Si
# otro portal exige el texto contrario, se corrige ahí mismo con
# request_user_input (nunca hace falta tocar código para eso).
PUBLICO_EN_GENERAL = {
    "rfc": "XAXX010101000",
    "razon_social": "CLIENTE GENERICO",
    "regimen_fiscal": "616",
}
USO_CFDI_PUBLICO_EN_GENERAL = "S01"


def _seed_dir() -> Path:
    for base in (Path.cwd(), Path(__file__).resolve().parents[3]):
        if (base / "seed" / "company.json").exists():
            return base / "seed"
    return Path.cwd() / "seed"


def get_fiscal_profile() -> dict:
    """Perfil fiscal del receptor (spec #11: autorización fiscal delegada,
    no es la e.firma). Fuente: `seed/company.json` (RFC, régimen, email)."""
    p = _seed_dir() / "company.json"
    if not p.exists():
        raise ValueError("sin seed/company.json: no hay perfil fiscal")
    return json.loads(p.read_text(encoding="utf-8"))


def match_candidates(extraction: dict[str, Any], transactions: list[Transaction],
                     limit: int = 5) -> list[dict]:
    """Candidatos de conciliación ticket<->movimiento.

    Reutiliza EXACTAMENTE `reconcile.amount_score/date_score/merchant_score`
    (spec #17): el ticket se compara contra cada egreso con la misma
    fórmula monto*0.50 + fecha*0.20 + comercio*0.30, sin duplicar lógica.
    Solo egresos: un ticket es siempre un gasto propio.
    """
    total = Decimal(str(extraction.get("total"))) if extraction.get("total") else None
    fecha_raw = extraction.get("fecha")
    fecha = datetime.fromisoformat(fecha_raw) if fecha_raw else None
    comercio = extraction.get("comercio") or ""

    out = []
    for t in transactions:
        if t.type != "egreso":
            continue
        am = rc.amount_score(t.amount, total) if total is not None else Decimal("0")
        fe = rc.date_score(t.date, fecha) if fecha is not None else Decimal("0")
        co = rc.merchant_score(t.merchant_name, comercio)
        score = am * Decimal("0.50") + fe * Decimal("0.20") + co * Decimal("0.30")
        out.append({
            "transaction_id": t.id, "score": score,
            "amount_score": am, "date_score": fe, "merchant_score": co,
            "merchant_name": t.merchant_name, "amount": t.amount, "date": t.date,
        })
    out.sort(key=lambda x: x["score"], reverse=True)
    return out[:limit]


def build_invoice_payload(extraction: dict[str, Any], fiscal_profile: dict,
                          uso_cfdi: str = "G03") -> dict:
    """Datos REALES para el browser agent. Nunca incluye nada inventado:
    lo que Vision no leyó llega en null y el agente debe pedirlo
    (`request_user_input`, spec #19) en vez de adivinar."""
    return {
        "comercio": extraction.get("comercio"),
        "rfc_comercio": extraction.get("rfc_comercio"),
        "total": extraction.get("total"),
        "fecha": extraction.get("fecha"),
        "folio_ticket": extraction.get("folio"),
        "rfc_receptor": fiscal_profile.get("rfc"),
        "razon_social_receptor": fiscal_profile.get("razon_social"),
        "regimen_fiscal_receptor": fiscal_profile.get("regimen_fiscal"),
        "cp_receptor": fiscal_profile.get("cp"),
        "email_receptor": fiscal_profile.get("email"),
        "uso_cfdi": uso_cfdi,
    }


def reconcile_cfdi(sb: Any, company_id: str, transaction_id: str,
                   cfdi_xml: str | None = None) -> dict:
    """CFDI real obtenido del portal -> reconciliación real (spec #3.3
    caso 1, último paso). Si el portal entrega el XML descargable, se
    parsea con el parser REAL (`integrations/sat/cfdi_xml.py`) y se
    guarda como CFDI recibido normal: la próxima lectura de `data.get_*`
    ya lo concilia con `reconcile.conciliar` sin lógica especial aquí.

    Sin XML (el portal solo mostró folio/UUID en pantalla) se documenta
    como reconciliación manual: honesto, no se inventa un CFDI.
    """
    from app import data
    from app.integrations.sat import cfdi_xml as cx
    from app.repositories import cfdi_repo

    if not cfdi_xml:
        return {"status": "manual", "transaction_id": transaction_id,
                "detalle": "portal no entregó XML descargable; sin CFDI real que conciliar"}

    perfil = get_fiscal_profile()
    cfdi = cx.parsear_xml(cfdi_xml, company_id, perfil["rfc"])
    cfdi_repo.upsert_cfdis(sb, [cfdi])
    data.get_cfdis.cache_clear()
    data.get_matches.cache_clear()
    return {"status": "reconciled", "transaction_id": transaction_id,
            "cfdi_uuid": cfdi.uuid}
