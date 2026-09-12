"""Reglas del Analista (spec #3.2): de números a alertas accionables.

Cada alerta trae copy corto + payload con pista de UI generativa
(componente del registry, spec #22) para que T8 la renderice.
El Analista (LLM) redacta sobre estas alertas; nunca las inventa.
"""

from __future__ import annotations

from decimal import Decimal

from app.financial import engine as en
from app.financial import reconcile as rc
from app.schemas.cfdi import Cfdi
from app.schemas.match import Match
from app.schemas.transaction import Transaction

CERO = Decimal("0")


def _pct(x: Decimal | None) -> str:
    return "s/d" if x is None else f"{(x * 100):.0f}%"


def _mxn(x: Decimal) -> str:
    return f"${x:,.2f}"


def _banco_mes(txns: list[Transaction], anio: int, mes: int) -> tuple[Decimal, Decimal, Decimal]:
    """Totales bancarios del mes (todo flujo incl. internos) + margen."""
    fm = [t for t in txns if t.date.year == anio and t.date.month == mes]
    ventas = sum((t.amount for t in fm if t.type == "ingreso"), CERO)
    gastos = sum((t.amount for t in fm if t.type == "egreso"), CERO)
    margen = ((ventas - gastos) / ventas) if ventas > 0 else CERO
    return ventas, gastos, margen


def _banco_mes_previo(txns: list[Transaction], anio: int, mes: int):
    prev_m, prev_a = (mes - 1, anio) if mes > 1 else (12, anio - 1)
    v, g, _ = _banco_mes(txns, prev_a, prev_m)
    return (None, None, None) if v == 0 and g == 0 else (v, g, (v - g) / v if v > 0 else CERO)


def _efectivo_a_fin_de_mes(txns: list[Transaction], anio: int, mes: int) -> Decimal:
    """Último saldo bancario con fecha dentro del mes (no el global)."""
    previas = sorted(
        (t for t in txns if (t.date.year, t.date.month) <= (anio, mes)
         and t.balance is not None),
        key=lambda t: (t.date, t.id),
    )
    return previas[-1].balance if previas else CERO


def generar_alertas(txns: list[Transaction], cfdis: list[Cfdi],
                    matches: list[Match], anio: int, mes: int,
                    company_id: str) -> list[dict]:
    mes_id = f"{anio}-{mes:02d}"
    alertas: list[dict] = []

    def _add(rule: str, severity: str, titulo: str, detalle: str,
             total: Decimal | None = None, payload: dict | None = None):
        alertas.append({
            "id": f"{mes_id}_{rule}", "company_id": company_id, "month": mes_id,
            "rule": rule, "severity": severity, "titulo": titulo,
            "detalle": detalle, "total": total, "estado": "abierta",
            "payload": payload or {},
        })

    # 1. gastos sin factura (acumulado abierto, no solo del mes: es backlog
    # por resolver; el mes de la alerta es solo contexto "a la fecha")
    sin = [m for m in matches
           if m.status == "unmatched"
           and (t := next((x for x in txns if x.id == m.transaction_id), None))
           and t.type == "egreso"]
    if sin:
        total = sum(
            (next(x for x in txns if x.id == m.transaction_id).amount for m in sin),
            CERO,
        )
        _add("sin_factura", "warning",
             f"{len(sin)} gasto{'s' if len(sin) != 1 else ''} necesita{'n' if len(sin) != 1 else ''} factura",
             f"Suman {_mxn(total)} sin CFDI asociado.",
             total, {"component": "receipts_resolution",
                     "props": {"count": len(sin), "total": str(total)}})

    # 2. cuentas por cobrar abiertas (acumuladas, no solo del mes)
    recs = rc.detectar_cxc(cfdis, matches, company_id)
    if recs:
        total = sum((r.amount_pending or CERO for r in recs), CERO)
        _add("cuentas_por_cobrar", "warning",
             f"{len(recs)} factura{'s' if len(recs) != 1 else ''} pendiente{'s' if len(recs) != 1 else ''} de cobro",
             f"Suman {_mxn(total)} en facturas emitidas sin cobro.",
             total, {"component": "receivables_resolution",
                     "props": {"count": len(recs), "total": str(total)}})

    # 3-5. tendencias MoM sobre TOTALES BANCARIOS del mes (la realidad de
    # caja de esta cuenta; el motor operativo queda para el Consultor).
    # Sin mes previo con datos: silencio, no invento tendencias.
    ventas, gastos, margen = _banco_mes(txns, anio, mes)
    pv, pg, pm = _banco_mes_previo(txns, anio, mes)
    if pv is not None and pg is not None and pm is not None:
        cv = en.mom(pv, ventas)
        cg = en.mom(pg, gastos)
        if cv is not None and cg is not None and (cg - cv) > Decimal("0.10"):
            _add("gasto_vs_ventas", "warning",
                 "Tus gastos crecen más rápido que tus ventas",
                 f"Gastos {_pct(cg)} vs ventas {_pct(cv)} el último mes.")
        if (pm - margen) > Decimal("0.03"):
            _add("margen_caida", "warning", "Tu margen se está comprimiendo",
                 f"Cayó de {_pct(pm)} a {_pct(margen)}.")
    # runway con el burn del mes y la caja A FIN DE ESE MES
    cf = en.cash_flow(txns, anio, mes)
    burn = -cf["neto"] if cf["neto"] < 0 else CERO
    efectivo = _efectivo_a_fin_de_mes(txns, anio, mes)
    if burn > 0:
        dias = int(efectivo / (burn / 30))
        if dias < 30:
            _add("efectivo_bajo", "critical",
                 f"Te quedan ~{max(dias, 0)} días de efectivo",
                 f"Con el ritmo actual ({_mxn(burn)}/mes) y {_mxn(efectivo)} en caja.")
        elif dias < 90:
            _add("efectivo_bajo", "warning",
                 f"Tu colchón es de ~{dias} días",
                 f"Con el ritmo actual ({_mxn(burn)}/mes) y {_mxn(efectivo)} en caja.")
    return alertas
