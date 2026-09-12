"""Financial Engine — cálculo 100% determinístico, cero LLM (spec #9/#18).

Todo opera sobre listas de contratos (Transaction, Cfdi, Match). Los agentes
interpretan estos números; nunca los calculan.

Convenciones:
- Dinero en Decimal. Tasas como Decimal (0.16, 0.30).
- Traspasos internos (es_interno) se excluyen de ventas/gastos: no son
  flujo operativo (esta cuenta se fondea desde BBVA).
- Las devoluciones ya vienen neteadas en Transaction (tipo por flujo neto).
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from app.schemas.cfdi import Cfdi
from app.schemas.transaction import Transaction

CERO = Decimal("0")
IVA = Decimal("0.16")
ISR = Decimal("0.30")


def del_mes(txns: list[Transaction], anio: int, mes: int) -> list[Transaction]:
    return [t for t in txns if t.date.year == anio and t.date.month == mes]


def operativos(txns: list[Transaction]) -> list[Transaction]:
    """Flujo operativo: fuera traspasos internos."""
    return [t for t in txns if not t.es_interno]


def _suma(txns: list[Transaction], tipo: str) -> Decimal:
    return sum((t.amount for t in txns if t.type == tipo), CERO)


def income_statement(txns: list[Transaction], anio: int, mes: int) -> dict:
    """Estado de resultados del mes (operativo, sin internos)."""
    fm = operativos(del_mes(txns, anio, mes))
    ventas = _suma(fm, "ingreso")
    gastos = _suma(fm, "egreso")
    utilidad = ventas - gastos
    por_categoria: dict[str, Decimal] = {}
    for t in fm:
        if t.type == "egreso":
            por_categoria[t.categoria] = por_categoria.get(t.categoria, CERO) + t.amount
    return {
        "ventas": ventas, "gastos": gastos, "utilidad": utilidad,
        "margen": (utilidad / ventas) if ventas > 0 else CERO,
        "por_categoria": por_categoria,
    }


def cash_flow(txns: list[Transaction], anio: int, mes: int) -> dict:
    """Flujo de efectivo: TODO el flujo bancario (incluye internos)."""
    fm = del_mes(txns, anio, mes)
    entradas = _suma(fm, "ingreso")
    salidas = _suma(fm, "egreso")
    return {"entradas": entradas, "salidas": salidas, "neto": entradas - salidas}


def balance_sheet(txns: list[Transaction], cfdis: list[Cfdi],
                  matches: dict[str, str | None]) -> dict:
    """Balance simplificado y honesto: caja + CxC. Sin pasivos registrados.

    matches: {transaction_id: cfdi_uuid|None} para emitidos (ver reconcile).
    """
    ordenados = sorted(txns, key=lambda t: (t.date, t.id))
    efectivo = ordenados[-1].balance if ordenados and ordenados[-1].balance is not None else CERO
    cxc = sum(
        (c.total for c in cfdis
         if c.tipo == "emitido" and c.uuid not in set(matches.values())),
        CERO,
    )
    activo = efectivo + cxc
    return {
        "efectivo": efectivo, "cuentas_por_cobrar": cxc,
        "activo_total": activo, "pasivo_total": CERO,
        "capital_contable": activo, "nota": "sin pasivos registrados",
    }


def mom(anterior: Decimal, actual: Decimal) -> Decimal | None:
    """Crecimiento mes-a-mes. None si no hay base."""
    if anterior == 0:
        return None
    return (actual - anterior) / abs(anterior)


def metrics(txns: list[Transaction], anio: int, mes: int) -> dict:
    """Métricas + tendencias MoM (necesita mes previo con datos)."""
    actual = income_statement(txns, anio, mes)
    cf = cash_flow(txns, anio, mes)
    prev_m, prev_a = (mes - 1, anio) if mes > 1 else (12, anio - 1)
    prev = income_statement(txns, prev_a, prev_m)
    out = {
        "ventas": actual["ventas"], "gastos": actual["gastos"],
        "utilidad": actual["utilidad"], "margen": actual["margen"],
        "flujo_neto": cf["neto"],
        "crec_ventas": mom(prev["ventas"], actual["ventas"]),
        "crec_gastos": mom(prev["gastos"], actual["gastos"]),
        "margen_previo": prev["margen"] if (prev["ventas"] > 0) else None,
    }
    # runway en días con el burn (salidas netas) del mes
    burn = -cf["neto"] if cf["neto"] < 0 else CERO
    out["burn_mensual"] = burn
    return out


def estimate_taxes(txns: list[Transaction], anio: int, mes: int) -> dict:
    """Impuesto estimado: provisión ISR 30% sobre utilidad positiva +
    pagos referenciados reales del mes (dato, no estimación)."""
    inc = income_statement(txns, anio, mes)
    provision = (inc["utilidad"] * ISR).quantize(Decimal("0.01")) if inc["utilidad"] > 0 else CERO
    pagado = sum(
        (t.amount for t in del_mes(txns, anio, mes)
         if t.type == "egreso" and t.categoria == "impuestos"),
        CERO,
    )
    return {"provision_isr": provision, "pagos_referenciados": pagado,
            "nota": "provisión simple 30% sobre utilidad; T-consultor la interpreta"}


def simulate_hiring(txns: list[Transaction], anio: int, mes: int,
                    monthly_cost: Decimal) -> dict:
    """¿Aguanta la nómina? Matemática pura; el Consultor la interpreta."""
    m = metrics(txns, anio, mes)
    ordenados = sorted(txns, key=lambda t: (t.date, t.id))
    efectivo = ordenados[-1].balance or CERO
    cubre_con_utilidad = m["utilidad"] >= monthly_cost
    burn_nuevo = m["burn_mensual"] + monthly_cost
    runway_dias = int(efectivo / (burn_nuevo / 30)) if burn_nuevo > 0 else None
    if cubre_con_utilidad:
        veredicto = "viable"
    elif runway_dias is not None and runway_dias >= 180:
        veredicto = "viable_con_reservas"
    elif runway_dias is not None and runway_dias >= 90:
        veredicto = "riesgosa"
    else:
        veredicto = "no_viable"
    return {
        "monthly_cost": monthly_cost, "utilidad_mensual": m["utilidad"],
        "cubre_con_utilidad": cubre_con_utilidad,
        "burn_nuevo_mensual": burn_nuevo, "runway_dias": runway_dias,
        "veredicto": veredicto,
    }


def simulate_loan(utilidad_mensual: Decimal, amount: Decimal,
                  annual_rate: Decimal, months: int) -> dict:
    """Crédito con amortización francesa. Cobertura = utilidad / pago."""
    r = annual_rate / 12
    n = months
    if r == 0:
        pago = amount / n
    else:
        pago = amount * r / (1 - (1 + r) ** (-n))
    pago = pago.quantize(Decimal("0.01"))
    cobertura = (utilidad_mensual / pago) if pago > 0 else None
    if cobertura is None or cobertura < 1:
        veredicto = "no_viable"
    elif cobertura < Decimal("1.5"):
        veredicto = "ajustada"
    else:
        veredicto = "viable"
    return {
        "amount": amount, "annual_rate": annual_rate, "months": months,
        "pago_mensual": pago, "total_intereses": pago * n - amount,
        "cobertura_con_utilidad": cobertura, "veredicto": veredicto,
    }


def ultimo_dia_con_saldo(txns: list[Transaction]) -> date | None:
    ordenados = sorted(txns, key=lambda t: (t.date, t.id))
    return ordenados[-1].date.date() if ordenados else None


def banco_mes(txns: list[Transaction], anio: int, mes: int) -> tuple[Decimal, Decimal, Decimal]:
    """Totales bancarios del mes (todo flujo) + margen. Análisis horizontal."""
    fm = [t for t in txns if t.date.year == anio and t.date.month == mes]
    ventas = sum((t.amount for t in fm if t.type == "ingreso"), CERO)
    gastos = sum((t.amount for t in fm if t.type == "egreso"), CERO)
    margen = ((ventas - gastos) / ventas) if ventas > 0 else CERO
    return ventas, gastos, margen


def efectivo_a_fin_de_mes(txns: list[Transaction], anio: int, mes: int) -> Decimal:
    """Último saldo bancario con fecha dentro del mes."""
    previas = sorted(
        (t for t in txns if (t.date.year, t.date.month) <= (anio, mes)
         and t.balance is not None),
        key=lambda t: (t.date, t.id),
    )
    return previas[-1].balance if previas else CERO


def signals(txns: list[Transaction], anio: int, mes: int) -> dict:
    """Señales numéricas para el Analista (fórmulas estándar, sin juicio).

    - Tasas de crecimiento MoM (análisis horizontal) + brecha en pp.
    - Margen del mes y delta vs previo en pp.
    - runway_dias = efectivo / (burn/30) (cash runway estándar).
    - Grado de apalancamiento operativo DOL = %Δutilidad / %Δventas.
    - Concentración del gasto por categoría y dependencia de fondeo interno.
    El Analista decide cuáles merecen alerta y tarjeta en la UI.
    """
    ventas, gastos, margen = banco_mes(txns, anio, mes)
    prev_m, prev_a = (mes - 1, anio) if mes > 1 else (12, anio - 1)
    pv, pg, pm = banco_mes(txns, prev_a, prev_m)
    con_previo = not (pv == 0 and pg == 0)
    cv = mom(pv, ventas) if con_previo else None
    cg = mom(pg, gastos) if con_previo else None
    cf = cash_flow(txns, anio, mes)
    burn = -cf["neto"] if cf["neto"] < 0 else CERO
    efectivo = efectivo_a_fin_de_mes(txns, anio, mes)
    por_cat: dict[str, Decimal] = {}
    for t in del_mes(txns, anio, mes):
        if t.type == "egreso" and not t.es_interno:
            por_cat[t.categoria] = por_cat.get(t.categoria, CERO) + t.amount
    dep_int = sum((t.amount for t in del_mes(txns, anio, mes)
                   if t.type == "ingreso" and t.es_interno), CERO)
    # DOL con cuidado: sin base o sin cambio en ventas no se define
    dol = None
    if con_previo and cv:
        util_prev = pv - pg
        du = mom(util_prev, ventas - gastos)
        dol = (du / cv) if du is not None else None
    return {
        "crec_ventas": cv, "crec_gastos": cg,
        "brecha_pp": (cg - cv) if (cv is not None and cg is not None) else None,
        "margen": margen, "margen_previo": pm if con_previo else None,
        "margen_delta_pp": (margen - pm) if con_previo else None,
        "burn_mensual": burn, "efectivo": efectivo,
        "runway_dias": int(efectivo / (burn / 30)) if burn > 0 else None,
        "operating_leverage": dol,
        "gasto_por_categoria": por_cat,
        "fondeo_interno": dep_int,
        "ratio_fondeo_interno": (dep_int / ventas) if ventas > 0 else CERO,
    }
