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

import calendar
import statistics
from datetime import date, timedelta
from decimal import Decimal

from app.schemas.cfdi import Cfdi
from app.schemas.match import Match
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


def compare_credit_options(utilidad_mensual: Decimal, amount: Decimal,
                           options: list[dict],
                           months: int | None = None) -> dict:
    """Compara catálogo (mock Banorte) para un monto: pago, costo y cobertura.

    Ordena viables por costo total (intereses + apertura). Recomienda la
    viable más barata; si ninguna es viable lo dice con el pago mínimo.
    Determinista: el Consultor solo interpreta el ranking.
    """
    filas: list[dict] = []
    for op in options:
        omin, omax = Decimal(op["monto_min"]), Decimal(op["monto_max"])
        if not (omin <= amount <= omax):
            continue
        for n in op["plazos_meses"]:
            if months is not None and n != months:
                continue
            sim = simulate_loan(utilidad_mensual, amount,
                                Decimal(op["tasa_anual"]), int(n))
            comision = (amount * Decimal(op.get("comision_apertura_pct", "0"))
                        ).quantize(Decimal("0.01"))
            filas.append({
                "option_id": op["id"], "nombre": op["nombre"],
                "tasa_anual": op["tasa_anual"], "plazo_meses": int(n),
                "pago_mensual": sim["pago_mensual"],
                "total_intereses": sim["total_intereses"],
                "comision_apertura": comision,
                "costo_total": sim["total_intereses"] + comision,
                "cobertura": sim["cobertura_con_utilidad"],
                "veredicto": sim["veredicto"],
            })
    viables = sorted(
        (f for f in filas if f["veredicto"] == "viable"),
        key=lambda f: f["costo_total"])
    ajustadas = sorted(
        (f for f in filas if f["veredicto"] == "ajustada"),
        key=lambda f: f["costo_total"])
    recomendada = (viables or ajustadas or [None])[0]
    return {
        "amount": amount, "opciones_evaluadas": len(filas),
        "ranking": sorted(filas, key=lambda f: (f["veredicto"] != "viable",
                                                f["costo_total"])),
        "recomendada": recomendada,
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


def signals(txns: list[Transaction], cfdis: list[Cfdi], matches: list[Match],
             anio: int, mes: int) -> dict:
    """Señales numéricas generales para el Analista (fórmulas, sin juicio).

    Agnosticas al negocio: sirven a sanos y en burn. Familias:
    crecimiento (tasas, tickets, base clientes, HHI), rentabilidad
    (márgenes, burn multiple, regla 40, DOL), liquidez (burn, runway,
    cobertura fijos, racha, volatilidad, DSO), fiscal (IVA neto,
    deducibilidad, brecha pagos), comercial CxC y estructura.
    El Analista decide cuáles merecen alerta y tarjeta en la UI.
    """
    from app.financial.reconcile import es_conciliable

    fin_mes = date(anio, mes, calendar.monthrange(anio, mes)[1])
    fm = del_mes(txns, anio, mes)
    ventas, gastos, margen = banco_mes(txns, anio, mes)
    prev_m, prev_a = (mes - 1, anio) if mes > 1 else (12, anio - 1)
    pv, pg, pm = banco_mes(txns, prev_a, prev_m)
    con_previo = not (pv == 0 and pg == 0)
    cv = mom(pv, ventas) if con_previo else None
    cg = mom(pg, gastos) if con_previo else None
    cf = cash_flow(txns, anio, mes)
    burn = -cf["neto"] if cf["neto"] < 0 else CERO
    efectivo = efectivo_a_fin_de_mes(txns, anio, mes)

    # --- crecimiento: tickets y base de clientes (cobros no internos) ---
    cobros = sorted((t.amount for t in fm
                     if t.type == "ingreso" and not t.es_interno))
    def _cli_key(t: Transaction) -> str:
        return (t.merchant_rfc or t.merchant_name or "?").upper()

    clientes_mes = {_cli_key(t) for t in fm
                    if t.type == "ingreso" and not t.es_interno}
    rfc_previos = {_cli_key(t) for t in txns
                   if (t.date.year, t.date.month) < (anio, mes)
                   and t.type == "ingreso" and not t.es_interno}
    tot_cob = sum(cobros, CERO)
    hhi_ing = (sum(((c / tot_cob) ** 2 for c in
                    _por_llave(fm, _cli_key, "ingreso")), CERO)
               if tot_cob > 0 else None)

    # --- rentabilidad ---
    dol = None
    if con_previo and cv:
        du = mom(pv - pg, ventas - gastos)
        dol = (du / cv) if du is not None else None
    fees = sum((t.amount for t in fm if t.type == "egreso"
                and t.categoria in ("comision", "iva_comision")), CERO)

    # --- liquidez: racha y volatilidad de netos diarios ---
    racha_signo, racha_n = 0, 0
    a, m = anio, mes
    while True:
        net = cash_flow(txns, a, m)["neto"]
        hay = any((t.date.year, t.date.month) == (a, m) for t in txns)
        s = (1 if net > 0 else -1) if net != 0 else 0
        if not hay or (racha_n and s != racha_signo) or s == 0:
            break
        racha_signo, racha_n = s, racha_n + 1
        m, a = (m - 1, a) if m > 1 else (12, a - 1)
    netos_dia: dict[date, Decimal] = {}
    for t in fm:
        d = t.date.date()
        netos_dia[d] = netos_dia.get(d, CERO) + (t.amount if t.type == "ingreso" else -t.amount)
    vals = [float(v) for v in netos_dia.values()]
    volat = (statistics.pstdev(vals) / abs(statistics.mean(vals))) if len(vals) > 1 and statistics.mean(vals) != 0 else None
    fijos = sum((t.amount for t in fm if t.type == "egreso"
                 and t.categoria in ("domiciliacion", "servicios", "comision", "iva_comision")), CERO)

    # --- fiscal y comercial con CFDIs ---
    emi_mes = [c for c in cfdis if c.tipo == "emitido"
               and (c.fecha_emision.year, c.fecha_emision.month) == (anio, mes)]
    rec_mes = [c for c in cfdis if c.tipo == "recibido"
               and (c.fecha_emision.year, c.fecha_emision.month) == (anio, mes)]
    iva_t = sum((c.iva for c in emi_mes), CERO)
    iva_a = sum((c.iva for c in rec_mes), CERO)
    dev_mes = sum((c.total for c in emi_mes), CERO)
    por_uuid = {c.uuid: c for c in cfdis}
    abiertas = [c for c in cfdis if c.tipo == "emitido"
                and c.fecha_emision.date() <= fin_mes
                and not any(mm.transaction_id and mm.cfdi_id == c.uuid
                            and mm.status in ("auto", "review") for mm in matches)]
    tot_cxc = sum((c.total for c in abiertas), CERO)
    dev_tasa_diaria = dev_mes / 30 if dev_mes > 0 else None
    antig = [(fin_mes - c.fecha_emision.date()).days for c in abiertas]
    vencidas = sum(1 for c in abiertas
                   if (c.fecha_vencimiento.date() if c.fecha_vencimiento
                       else c.fecha_emision.date() + timedelta(days=30)) < fin_mes)
    por_cli: dict[str, Decimal] = {}
    for c in abiertas:
        por_cli[c.receptor_rfc] = por_cli.get(c.receptor_rfc, CERO) + c.total
    top_cxc = (max(por_cli.values()) / tot_cxc) if tot_cxc > 0 else None
    # deducibilidad: egresos conciliables del mes con match
    eleg = [t for t in fm if t.type == "egreso" and es_conciliable(t)]
    con_cfdi = sum(1 for t in eleg
                   if any(mm.transaction_id == t.id and mm.cfdi_id
                          and mm.status in ("auto", "review") for mm in matches))

    # --- estructura ---
    por_cat: dict[str, Decimal] = {}
    por_rubro: dict[str, Decimal] = {}
    for t in del_mes(txns, anio, mes):
        if t.type == "egreso" and not t.es_interno:
            por_cat[t.categoria] = por_cat.get(t.categoria, CERO) + t.amount
            por_rubro[t.rubro] = por_rubro.get(t.rubro, CERO) + t.amount
    directos = por_rubro.get("proveedores_materiales", CERO)
    dep_int = sum((t.amount for t in fm
                   if t.type == "ingreso" and t.es_interno), CERO)
    por_prov: dict[str, Decimal] = {}
    for t in fm:
        if t.type == "egreso" and not t.es_interno:
            por_prov[_cli_key(t)] = por_prov.get(_cli_key(t), CERO) + t.amount
    tot_prov = sum(por_prov.values(), CERO)
    hhi_prov = (sum(((v / tot_prov) ** 2 for v in por_prov.values()), CERO)
                if tot_prov > 0 else None)
    masa = sum((t.amount for t in fm if t.type == "egreso"
                and "NOMINA" in t.description.upper()), CERO)
    provision = (estimate_taxes(txns, anio, mes)["provision_isr"])
    pagados = sum((t.amount for t in fm if t.type == "egreso"
                   and t.categoria == "impuestos"), CERO)

    return _redondear({
        # base
        "ventas": ventas, "gastos": gastos, "utilidad": ventas - gastos,
        "tiene_datos": len(fm) > 0, "n_movimientos": len(fm),
        # crecimiento
        "crec_ventas": cv, "crec_gastos": cg,
        "brecha_pp": (cg - cv) if (cv is not None and cg is not None) else None,
        "ticket_promedio_ingreso": (tot_cob / len(cobros)) if cobros else None,
        "ticket_mediano_ingreso": statistics.median(cobros) if cobros else None,
        "clientes_activos_mes": len(clientes_mes),
        "clientes_nuevos_mes": len(clientes_mes - rfc_previos),
        "hhi_ingresos": hhi_ing,
        # rentabilidad
        "margen": margen, "margen_previo": pm if con_previo else None,
        "margen_delta_pp": (margen - pm) if con_previo else None,
        "margen_operativo_excl_comisiones": (((ventas - (gastos - fees)) / ventas)
                                             if ventas > 0 else CERO),
        "burn_multiple": (burn / ventas) if (burn > 0 and ventas > 0) else CERO,
        "regla_40": ((cv + margen) if cv is not None else None),
        "operating_leverage": dol,
        # liquidez
        "burn_mensual": burn, "efectivo": efectivo,
        "runway_dias": int(efectivo / (burn / 30)) if burn > 0 else None,
        "cobertura_gastos_fijos": (efectivo / fijos) if fijos > 0 else None,
        "racha_signo": racha_signo, "racha_meses": racha_n,
        "volatilidad_flujo": volat,
        "dso_dias": (CERO if tot_cxc == 0 else
                     (tot_cxc / dev_tasa_diaria) if dev_tasa_diaria else None),
        # fiscal
        "iva_trasladado": iva_t, "iva_acreditable": iva_a,
        "iva_neto": iva_t - iva_a,
        "pct_gasto_deducible": (Decimal(con_cfdi) / len(eleg)) if eleg else None,
        "brecha_pagos_provision": pagados - provision,
        # comercial CxC
        "cxc_total": tot_cxc, "cxc_count": len(abiertas),
        "cxc_antiguedad_promedio_dias": (sum(antig) / len(antig)) if antig else None,
        "cxc_pct_vencida": (Decimal(vencidas) / len(abiertas)) if abiertas else None,
        "cxc_top_cliente": top_cxc,
        # estructura
        "gasto_por_categoria": por_cat,
        "gasto_por_rubro": por_rubro,
        "margen_bruto_proxy": (((ventas - directos) / ventas)
                               if ventas > 0 else CERO),
        "fondeo_interno": dep_int,
        "ratio_fondeo_interno": (dep_int / ventas) if ventas > 0 else CERO,
        "hhi_gasto_proveedores": hhi_prov,
        "masa_salarial_estimada": masa,
    })


def _redondear(s: dict) -> dict:
    """Ratios a 4 decimales y dinero a 2: menos ruido para el lector (y la IA)."""
    ratios = {"crec_ventas", "crec_gastos", "brecha_pp", "margen",
              "margen_previo", "margen_delta_pp",
              "margen_operativo_excl_comisiones", "burn_multiple", "regla_40",
              "operating_leverage", "hhi_ingresos", "hhi_gasto_proveedores",
              "ratio_fondeo_interno", "pct_gasto_deducible", "cxc_top_cliente",
              "cxc_pct_vencida", "cobertura_gastos_fijos",
              "margen_bruto_proxy"}
    dinero = {"ticket_promedio_ingreso", "ticket_mediano_ingreso", "dso_dias"}
    out = {}
    for k, v in s.items():
        if isinstance(v, Decimal) and k in ratios:
            out[k] = v.quantize(Decimal("0.0001"))
        elif isinstance(v, Decimal) and k in dinero:
            out[k] = v.quantize(Decimal("0.01"))
        else:
            out[k] = v
    return out


def brief_mensual(s: dict, anio: int, mes: int) -> list[str]:
    """Verbalización determinística de señales (formato, cero juicio).

    Lee en voz alta los números para que el modelo no los malinterprete.
    Sin adjetivos: el juicio es del Analista.
    """
    mes_id = f"{anio}-{mes:02d}"

    def pct(x):
        if x is None:
            return "s/d"
        return f"{'+' if x >= 0 else ''}{float(x) * 100:.1f}%"

    def mxn(x):
        return f"${float(x):,.2f}"

    if not s.get("tiene_datos"):
        return [f"{mes_id}: SIN MOVIMIENTOS registrados (no es caída, es mes vacío)."]
    b = [
        f"ventas {mes_id}: {mxn(s['ventas'])} ({pct(s['crec_ventas'])} vs mes previo)",
        f"gastos {mes_id}: {mxn(s['gastos'])} ({pct(s['crec_gastos'])} vs mes previo)",
        f"margen: {pct(s['margen'])} (previo {pct(s['margen_previo'])})",
        f"efectivo a fin de mes: {mxn(s['efectivo'])}; burn mensual {mxn(s['burn_mensual'])}; runway {s['runway_dias']} días",
        f"CxC abiertas: {s['cxc_count']} por {mxn(s['cxc_total'])}; vencidas {pct(s['cxc_pct_vencida'])}; DSO {s['dso_dias']} días",
        f"fondeo interno del mes: {mxn(s['fondeo_interno'])} ({pct(s['ratio_fondeo_interno'])} de ingresos)",
        f"gasto deducible con CFDI: {pct(s['pct_gasto_deducible'])}",
        f"IVA del mes: trasladado {mxn(s['iva_trasladado'])}, acreditable {mxn(s['iva_acreditable'])}",
    ]
    return b


def _por_llave(fm: list[Transaction], llave, tipo: str) -> list[Decimal]:
    acc: dict[str, Decimal] = {}
    for t in fm:
        if t.type == tipo and not t.es_interno:
            acc[llave(t)] = acc.get(llave(t), CERO) + t.amount
    return list(acc.values())
