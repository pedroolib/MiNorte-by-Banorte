"""Reconciliación determinística Banorte vs CFDI (spec #17).

Score por pareja (mismo sentido: egreso↔recibido, ingreso↔emitido):
    score = monto*0.50 + fecha*0.20 + comercio*0.30
    >= 0.85 → auto | 0.60–0.85 → review | < 0.60 → unmatched

- monto: 1.0 si exacto, decae lineal (10% de diferencia → 0).
- fecha: 1.0 mismo día, decae a 0 en ±15 días (ventana cross-mes).
- comercio: RapidFuzz token_set_ratio sobre nombres normalizados.

Asignación greedy determinista por (fecha, id): cada CFDI se usa una vez.
Sin IA: la misma función sirve para detectar CxC (emitido sin cobro).
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta
from decimal import Decimal

from rapidfuzz import fuzz

from app.schemas.cfdi import Cfdi
from app.schemas.match import Match
from app.schemas.receivable import Receivable
from app.schemas.transaction import Transaction

AUTO = Decimal("0.85")
REVIEW = Decimal("0.60")
VENTANA_DIAS = 15

# Categorías fuera de conciliación (sin CFDI por definición)
NO_CONCILIABLE = {"comision", "iva_comision", "impuestos"}


def es_conciliable(t: Transaction) -> bool:
    if t.es_interno or t.categoria in NO_CONCILIABLE:
        return False
    if t.type == "ingreso":
        return t.categoria == "spei_recibido"
    return bool(t.merchant_rfc)


def _norm(s: str) -> str:
    s = s.upper()
    s = re.sub(r"\b(SA DE CV|S\.A\. DE C\.V\.|S DE RL|DE CV)\b", " ", s)
    return re.sub(r"\s+", " ", re.sub(r"[^A-Z0-9Ñ ]", " ", s)).strip()


def amount_score(a: Decimal, b: Decimal) -> Decimal:
    if a == b:
        return Decimal("1")
    base = max(abs(a), abs(b))
    if base == 0:
        return Decimal("1")
    dif = abs(a - b) / base
    return max(Decimal("0"), Decimal("1") - dif * 10)


def date_score(f1: datetime, f2: datetime) -> Decimal:
    dias = abs((f1.date() - f2.date()).days)
    if dias > VENTANA_DIAS:
        return Decimal("0")
    return Decimal("1") - Decimal(dias) / Decimal(VENTANA_DIAS)


def merchant_score(n1: str, n2: str) -> Decimal:
    if not n1 or not n2:
        return Decimal("0")
    return Decimal(fuzz.token_set_ratio(_norm(n1), _norm(n2))) / 100


def score(t: Transaction, c: Cfdi) -> tuple[Decimal, Decimal, Decimal, Decimal]:
    """(total, monto, fecha, comercio)."""
    if t.type == "ingreso":
        nombre = c.receptor_nombre
    else:
        nombre = c.emisor_nombre
    am = amount_score(t.amount, c.total)
    fe = date_score(t.date, c.fecha_emision)
    co = merchant_score(t.merchant_name, nombre)
    total = am * Decimal("0.50") + fe * Decimal("0.20") + co * Decimal("0.30")
    return total, am, fe, co


def _estado(total: Decimal) -> str:
    if total >= AUTO:
        return "auto"
    if total >= REVIEW:
        return "review"
    return "unmatched"


def conciliar(txns: list[Transaction], cfdis: list[Cfdi]) -> list[Match]:
    """Concilia movimientos conciliables. Un CFDI se asigna una sola vez."""
    usados: set[str] = set()
    matches: list[Match] = []
    candidatos = sorted(
        [t for t in txns if es_conciliable(t)], key=lambda t: (t.date, t.id)
    )
    for t in candidatos:
        direccion = "emitido" if t.type == "ingreso" else "recibido"
        mejor = None  # (total, uuid, am, fe, co)
        for c in cfdis:
            if c.tipo != direccion or c.uuid in usados:
                continue
            if abs((t.date.date() - c.fecha_emision.date()).days) > VENTANA_DIAS:
                continue
            total, am, fe, co = score(t, c)
            if mejor is None or total > mejor[0]:
                mejor = (total, c.uuid, am, fe, co)
        if mejor is None or mejor[0] < REVIEW:
            matches.append(Match(
                transaction_id=t.id, cfdi_id=None,
                score=mejor[0] if mejor else Decimal("0"),
                amount_score=mejor[2] if mejor else Decimal("0"),
                date_score=mejor[3] if mejor else Decimal("0"),
                merchant_score=mejor[4] if mejor else Decimal("0"),
                status="unmatched",
            ))
        else:
            total, cuuid, am, fe, co = mejor
            usados.add(cuuid)
            matches.append(Match(
                transaction_id=t.id, cfdi_id=cuuid, score=total,
                amount_score=am, date_score=fe, merchant_score=co,
                status=_estado(total),
            ))
    return matches


def detectar_cxc(cfdis: list[Cfdi], matches: list[Match],
                 company_id: str, dias_credito: int = 30) -> list[Receivable]:
    """Emitidos sin cobro conciliado -> cuentas por cobrar abiertas."""
    cobrados = {m.cfdi_id for m in matches if m.cfdi_id}
    recs: list[Receivable] = []
    for c in cfdis:
        if c.tipo != "emitido" or c.uuid in cobrados:
            continue
        recs.append(Receivable(
            id=f"ar_{c.uuid[:8].lower()}",
            company_id=company_id,
            cfdi_id=c.uuid,
            customer_name=c.receptor_nombre,
            customer_rfc=c.receptor_rfc,
            amount=c.total,
            amount_paid=Decimal("0"),
            issued_at=c.fecha_emision,
            due_date=(c.fecha_emision + timedelta(days=dias_credito)),
            status="open",
        ))
    return recs
