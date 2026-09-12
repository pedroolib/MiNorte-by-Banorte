"""Alertas deterministas (spec #3.2, hechos accionables).

Solo reglas que son verificación, no interpretación:
- sin_factura: egresos conciliables sin CFDI (backlog acumulable).
- cuentas_por_cobrar: emitidos sin cobro conciliado.

Todo lo demás (tendencias, runway, concentración) lo calcula el motor
como SEÑALES (engine.signals, fórmulas estándar sin umbrales ni copy) y
el Analista decide qué merece alerta y tarjeta en la UI generativa.
Cada alerta trae payload con pista de componente (spec #22).
"""

from __future__ import annotations

from decimal import Decimal

from app.financial import reconcile as rc
from app.schemas.cfdi import Cfdi
from app.schemas.match import Match
from app.schemas.transaction import Transaction

CERO = Decimal("0")

REGLAS = ("sin_factura", "cuentas_por_cobrar")


def _mxn(x: Decimal) -> str:
    return f"${x:,.2f}"


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

    return alertas
