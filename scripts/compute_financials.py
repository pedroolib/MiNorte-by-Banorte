#!/usr/bin/env python3
"""Calcula y persiste finanzas: matches, CxC, snapshots y alertas.

Uso:
    uv run --project apps/api python scripts/compute_financials.py [--month YYYY-MM | --all]

Lee transactions+cfdis de Supabase, corre motor determinístico y guarda
resultados (idempotente por upserts con ids deterministas).
Requiere 003_financial.sql aplicado.
"""

from __future__ import annotations

import argparse
import sys
from decimal import Decimal
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "apps" / "api"))

from app.config import get_settings  # noqa: E402
from app.db import get_supabase  # noqa: E402
from app.financial import alerts as al  # noqa: E402
from app.financial import engine as en  # noqa: E402
from app.financial import reconcile as rc  # noqa: E402
from app.repositories import cfdi_repo, financial_repo as fr  # noqa: E402
from app.repositories import transactions_repo as tr  # noqa: E402


def meses_disponibles(txns) -> list[tuple[int, int]]:
    return sorted({(t.date.year, t.date.month) for t in txns})


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--month", default=None, help="YYYY-MM (default: último mes)")
    ap.add_argument("--all", action="store_true", help="computa todos los meses")
    args = ap.parse_args()

    s = get_settings()
    sb = get_supabase()
    if sb is None:
        sys.exit("Sin Supabase: pon SUPABASE_URL y SUPABASE_ANON_KEY en .env")
    company_id = s.COMPANY_ID

    try:
        txns = tr.fetch_ordered(sb, company_id)
        cfdis = cfdi_repo.fetch_all(sb, company_id)
    except Exception as e:
        sys.exit(f"No leo base ({e}). ¿Corriste 001/002 y make db-load?")
    assert txns and cfdis, "sin datos: corre make db-load primero"

    # 1. reconciliación global (±15 días cross-mes) + CxC
    matches = rc.conciliar(txns, cfdis)
    fr.upsert_matches(sb, company_id, matches)
    recs = rc.detectar_cxc(cfdis, matches, company_id)
    fr.upsert_receivables(sb, recs)
    auto = sum(1 for m in matches if m.status == "auto")
    rev = sum(1 for m in matches if m.status == "review")
    un = sum(1 for m in matches if m.status == "unmatched")
    print(f"matches: {len(matches)} (auto={auto} review={rev} unmatched={un})")
    print(f"CxC abiertas: {len(recs)} total=${sum((r.amount for r in recs), Decimal('0'))}")

    # 2. snapshots + alertas por mes
    meses = meses_disponibles(txns)
    if args.month:
        a, m = map(int, args.month.split("-"))
        meses = [(a, m)]
    elif not args.all:
        meses = meses[-1:]
    for anio, mes in meses:
        mes_id = f"{anio}-{mes:02d}"
        inc = en.income_statement(txns, anio, mes)   # operativo (sin internos)
        fm = en.del_mes(txns, anio, mes)
        # totales bancarios para el dashboard (coherentes con el spec)
        ventas_b = sum((t.amount for t in fm if t.type == "ingreso"), Decimal("0"))
        gastos_b = sum((t.amount for t in fm if t.type == "egreso"), Decimal("0"))
        cf = en.cash_flow(txns, anio, mes)
        met = en.metrics(txns, anio, mes)
        tax = en.estimate_taxes(txns, anio, mes)
        match_mes = {m.transaction_id: m.cfdi_id for m in matches}
        bal = en.balance_sheet(txns, cfdis, match_mes)
        alertas = al.generar_alertas(txns, cfdis, matches, anio, mes, company_id)
        fr.delete_month_alerts(sb, company_id, mes_id)  # reemplazo: sin fantasmas
        fr.upsert_alerts(sb, alertas)
        sin = next((a for a in alertas if a["rule"] == "sin_factura"), None)
        sig = en.signals(txns, anio, mes)

        def _js(v):
            if isinstance(v, Decimal):
                return str(v)
            if isinstance(v, dict):
                return {k: _js(x) for k, x in v.items()}
            return v

        fr.upsert_snapshot(sb, company_id, mes_id, {
            "ventas": ventas_b, "gastos": gastos_b,
            "utilidad": ventas_b - gastos_b,
            "margen": ((ventas_b - gastos_b) / ventas_b) if ventas_b > 0 else Decimal("0"),
            "efectivo": bal["efectivo"], "impuesto_estimado": tax["provision_isr"],
            "cxc_total": bal["cuentas_por_cobrar"], "flujo_neto": cf["neto"],
            "sin_cfdi_count": (sin["payload"]["props"]["count"] if sin else 0),
            "sin_cfdi_total": (sin["total"] if sin and sin["total"] is not None else Decimal("0")),
            "payload": {
                "ventas_operativas": str(inc["ventas"]),
                "gastos_operativos": str(inc["gastos"]),
                "por_categoria": {k: str(v) for k, v in inc["por_categoria"].items()},
                "crec_ventas": str(met["crec_ventas"]) if met["crec_ventas"] is not None else None,
                "crec_gastos": str(met["crec_gastos"]) if met["crec_gastos"] is not None else None,
                "pagos_referenciados": str(tax["pagos_referenciados"]),
                "signals": _js(sig),
            },
        })
        print(f"{mes_id}: ventas={ventas_b} gastos={gastos_b} "
              f"utilidad={ventas_b - gastos_b} "
              f"alertas={[a['rule'] for a in alertas]}")
    print("compute_financials OK")


if __name__ == "__main__":
    main()
