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


def amortizar_francesa(amount: Decimal, monthly_rate: Decimal, months: int) -> Decimal:
    """Primitiva determinista: pago mensual exacto. La usan el evaluador
    genérico, el comparador de créditos y /api/loans."""
    if months <= 0:
        raise ValueError("months debe ser >= 1")
    if amount < 0:
        raise ValueError("amount no acepta negativos")
    r = monthly_rate
    n = months
    pago = amount / n if r == 0 else amount * r / (1 - (1 + r) ** (-n))
    return pago.quantize(Decimal("0.01"))


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
            pago = amortizar_francesa(amount, Decimal(op["tasa_anual"]) / 12, int(n))
            total_intereses = pago * int(n) - amount
            cobertura = (utilidad_mensual / pago) if pago > 0 else None
            if cobertura is None or cobertura < 1:
                veredicto = "no_viable"
            elif cobertura < Decimal("1.5"):
                veredicto = "ajustada"
            else:
                veredicto = "viable"
            comision = (amount * Decimal(op.get("comision_apertura_pct", "0"))
                        ).quantize(Decimal("0.01"))
            filas.append({
                "option_id": op["id"], "nombre": op["nombre"],
                "tasa_anual": op["tasa_anual"], "plazo_meses": int(n),
                "pago_mensual": pago,
                "total_intereses": total_intereses,
                "comision_apertura": comision,
                "costo_total": total_intereses + comision,
                "cobertura": cobertura,
                "veredicto": veredicto,
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


def _cli_key(t: Transaction) -> str:
    return (t.merchant_rfc or t.merchant_name or "?").upper()


#: RFCs genéricos del SAT que NO identifican a nadie: ventas a público
#: en general (XAXX*) y operaciones con extranjeros (XAXE*). Agrupar por
#: ellos fusiona a todos los clientes en uno solo (cxc_top_cliente = 1.0
#: fantasma). Con estos o sin RFC, la entidad es el NOMBRE.
_RFC_GENERICOS = ("XAXX", "XAXE")


def _entidad_cfdi(c) -> str:
    """Llave de agrupación de un CFDI: RFC, con fallback a nombre.

    RFC real -> manda (un cliente con 2 nombres sigue siendo uno).
    RFC genérico o vacío -> nombre (CFDIs generados sin RFC verdadero).
    """
    rfc = (c.receptor_rfc or "").upper().strip()
    if rfc and not rfc.startswith(_RFC_GENERICOS):
        return rfc
    return (c.receptor_nombre or rfc or "?").upper().strip() or "?"

def _merch_key(t: Transaction) -> str:
    """Nivel entidad (no cuenta): un proveedor cobrado por 2 cuentas sigue
    siendo un proveedor. Los RFCs se reservan para joins de contacto."""
    return (t.merchant_name or "?").upper()


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
        k = _entidad_cfdi(c)
        por_cli[k] = por_cli.get(k, CERO) + c.total
    top_cxc = (max(por_cli.values()) / tot_cxc) if tot_cxc > 0 else None
    # deducibilidad: egresos conciliables del mes con match
    eleg = [t for t in fm if t.type == "egreso" and es_conciliable(t)]
    con_cfdi = sum(1 for t in eleg
                   if any(mm.transaction_id == t.id and mm.cfdi_id
                          and mm.status in ("auto", "review") for mm in matches))

    # --- estructura ---
    por_cat: dict[str, Decimal] = {}
    # rubro -> {total, n_negocios, top1:{nombre,total}, top1_share, hint_drill}
    por_rubro: dict[str, dict] = {}
    for t in del_mes(txns, anio, mes):
        if t.type == "egreso" and not t.es_interno:
            por_cat[t.categoria] = por_cat.get(t.categoria, CERO) + t.amount
            e = por_rubro.setdefault(t.rubro, {"total": CERO, "negocios": {}})
            e["total"] += t.amount
            k = _merch_key(t)
            n = e["negocios"].get(k)
            if n is None:
                e["negocios"][k] = {"nombre": t.merchant_name, "total": t.amount}
            else:
                n["total"] += t.amount
    rubros = {}
    for rubro, e in por_rubro.items():
        tops = sorted(e["negocios"].values(), key=lambda x: (-x["total"], x["nombre"]))
        top1 = tops[0] if tops else {"nombre": "", "total": CERO}
        share = (top1["total"] / e["total"]).quantize(Decimal("0.0001")) if e["total"] > 0 else CERO
        rubros[rubro] = {
            "total": e["total"], "n_negocios": len(tops),
            "top1": {"nombre": top1["nombre"], "total": top1["total"]},
            "top1_share": share,
            # hint determinista: concentrado o fragmentado → vale profundizar
            "hint_drill": bool(share > Decimal("0.25") or len(tops) >= 15),
        }
    directos = rubros.get("proveedores_materiales", {}).get("total", CERO)
    dep_int = sum((t.amount for t in fm
                   if t.type == "ingreso" and t.es_interno), CERO)
    por_prov: dict[str, Decimal] = {}
    for t in fm:
        if t.type == "egreso" and not t.es_interno:
            por_prov[_merch_key(t)] = por_prov.get(_merch_key(t), CERO) + t.amount
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
        "isr_estimado": provision,
        "pct_gasto_deducible": (Decimal(con_cfdi) / len(eleg)) if eleg else None,
        "brecha_pagos_provision": pagados - provision,
        # comercial CxC
        "cxc_total": tot_cxc, "cxc_count": len(abiertas),
        "cxc_antiguedad_promedio_dias": (sum(antig) / len(antig)) if antig else None,
        "cxc_pct_vencida": (Decimal(vencidas) / len(abiertas)) if abiertas else None,
        "cxc_top_cliente": top_cxc,
        # estructura
        "gasto_por_categoria": por_cat,
        "gasto_por_rubro": rubros,
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
    rubros = s.get("gasto_por_rubro", {}) or {}
    top_r = sorted(rubros.items(), key=lambda kv: kv[1]["total"], reverse=True)[:3]
    def _top_rubro(r):
        e = r[1]
        drill = " → drill sugerido" if e.get("hint_drill") else ""
        return f"{r[0]} {mxn(e['total'])} ({e['n_negocios']} negocios){drill}"
    b = [
        f"ventas {mes_id}: {mxn(s['ventas'])} ({pct(s['crec_ventas'])} vs mes previo)",
        f"gastos {mes_id}: {mxn(s['gastos'])} ({pct(s['crec_gastos'])} vs mes previo)",
        f"margen: {pct(s['margen'])} (previo {pct(s['margen_previo'])})",
        f"efectivo a fin de mes: {mxn(s['efectivo'])}; burn mensual {mxn(s['burn_mensual'])}; runway {s['runway_dias']} días",
        f"CxC abiertas: {s['cxc_count']} por {mxn(s['cxc_total'])}; vencidas {pct(s['cxc_pct_vencida'])}; DSO {s['dso_dias']} días",
        f"fondeo interno del mes: {mxn(s['fondeo_interno'])} ({pct(s['ratio_fondeo_interno'])} de ingresos)",
        f"gasto deducible con CFDI: {pct(s['pct_gasto_deducible'])}",
        f"IVA del mes: trasladado {mxn(s['iva_trasladado'])}, acreditable {mxn(s['iva_acreditable'])}",
        f"top rubros: {'; '.join(_top_rubro(r) for r in top_r) if top_r else 's/d'}",
    ]
    return b


def merchants_por_rubro(txns: list[Transaction], anio: int, mes: int,
                        rubro: str | None = None,
                        min_total: Decimal | float | int = 0,
                        limit: int = 50) -> list[dict]:
    """Nivel 1: detalle por comercio (filtrable). Orden total desc, desempate
    por nombre. Determinista: el agente decide cuántos traer."""
    from app.financial.categorias import normalizar_rubro

    codigo = normalizar_rubro(rubro)  # acepta "Proveedores de materiales"
    acc: dict[str, dict] = {}
    for t in del_mes(txns, anio, mes):
        if t.type != "egreso" or t.es_interno:
            continue
        if codigo is not None and t.rubro != codigo:
            continue
        k = _merch_key(t)
        n = acc.get(k)
        if n is None:
            acc[k] = {"nombre": t.merchant_name, "rubro": t.rubro,
                      "total": t.amount, "n_movs": 1}
        else:
            n["total"] += t.amount
            n["n_movs"] += 1
    minimo = Decimal(str(min_total))
    filas = [v for v in acc.values() if v["total"] >= minimo]
    filas.sort(key=lambda v: (-v["total"], v["nombre"]))
    return filas[: max(1, min(int(limit or 50), 200))]


def merchant_detail(txns: list[Transaction], nombre: str,
                    anio: int, mes: int, meses_atras: int = 6) -> dict:
    """Nivel 2: serie mensual de un comercio + recurrencia (caza-fugas)."""
    objetivo = (nombre or "").upper()
    serie: list[dict] = []
    a, m = anio, mes
    for _ in range(max(1, min(int(meses_atras or 6), 12))):
        fm = [t for t in del_mes(txns, a, m)
              if t.type == "egreso" and not t.es_interno
              and t.merchant_name.upper() == objetivo]
        tot = sum((t.amount for t in fm), CERO)
        serie.append({"month": f"{a}-{m:02d}", "total": tot, "n_movs": len(fm)})
        m, a = (m - 1, a) if m > 1 else (12, a - 1)
    serie.reverse()
    activos = [s for s in serie if s["n_movs"] > 0]
    tots = [s["total"] for s in activos]
    return {
        "nombre": nombre,
        "serie": serie,
        "meses_activo": len(activos),
        "recurrente": len(activos) >= 3,
        "ticket_promedio_mensual": (sum(tots, CERO) / len(tots)) if tots else CERO,
        "total_periodo": sum(tots, CERO),
    }


def _por_llave(fm: list[Transaction], llave, tipo: str) -> list[Decimal]:
    acc: dict[str, Decimal] = {}
    for t in fm:
        if t.type == tipo and not t.es_interno:
            acc[llave(t)] = acc.get(llave(t), CERO) + t.amount
    return list(acc.values())


# Catálogo de métricas: nombre -> (descripción, unidad, familia).
# Se deriva de las keys de signals(); si agregas una señal sin registrarla
# aquí, test_metric_catalog_cubre_signals falla a propósito.
METRIC_CATALOG: dict[str, dict] = {
    # base
    "ventas": ("Ventas del mes (cobros no internos).", "MXN", "base"),
    "gastos": ("Gastos del mes (pagos no internos).", "MXN", "base"),
    "utilidad": ("Ventas menos gastos.", "MXN", "base"),
    "tiene_datos": ("Si el mes tiene movimientos.", "bool", "base"),
    "n_movimientos": ("Número de movimientos del mes.", "conteo", "base"),
    # crecimiento
    "crec_ventas": ("Crecimiento MoM de ventas.", "tasa", "crecimiento"),
    "crec_gastos": ("Crecimiento MoM de gastos.", "tasa", "crecimiento"),
    "brecha_pp": ("Diferencia crec_gastos menos crec_ventas, en puntos.", "pp", "crecimiento"),
    "ticket_promedio_ingreso": ("Ticket promedio de cobro.", "MXN", "crecimiento"),
    "ticket_mediano_ingreso": ("Ticket mediano de cobro.", "MXN", "crecimiento"),
    "clientes_activos_mes": ("Clientes distintos que pagaron en el mes.", "conteo", "crecimiento"),
    "clientes_nuevos_mes": ("Clientes que pagan por primera vez.", "conteo", "crecimiento"),
    "hhi_ingresos": ("Concentración de ingresos 0-1 (1 = un solo cliente).", "índice", "crecimiento"),
    # rentabilidad
    "margen": ("Utilidad entre ventas.", "tasa", "rentabilidad"),
    "margen_previo": ("Margen del mes previo.", "tasa", "rentabilidad"),
    "margen_delta_pp": ("Cambio de margen en puntos.", "pp", "rentabilidad"),
    "margen_operativo_excl_comisiones": ("Margen sin comisiones bancarias.", "tasa", "rentabilidad"),
    "burn_multiple": ("Burn entre ventas (eficiencia).", "tasa", "rentabilidad"),
    "regla_40": ("Crecimiento más margen.", "tasa", "rentabilidad"),
    "operating_leverage": ("Apalancamiento operativo (%Δutilidad / %Δventas).", "tasa", "rentabilidad"),
    # liquidez
    "burn_mensual": ("Quema neta mensual (0 si hay superávit).", "MXN", "liquidez"),
    "efectivo": ("Saldo a fin de mes.", "MXN", "liquidez"),
    "runway_dias": ("Días de caja al ritmo actual.", "días", "liquidez"),
    "cobertura_gastos_fijos": ("Efectivo entre gastos fijos (veces).", "veces", "liquidez"),
    "racha_signo": ("Signo de la racha: 1 superávit, -1 burn, 0 corte.", "signo", "liquidez"),
    "racha_meses": ("Meses consecutivos con el mismo signo.", "meses", "liquidez"),
    "volatilidad_flujo": ("Coeficiente de variación de netos diarios.", "índice", "liquidez"),
    "dso_dias": ("Días de cobro pendientes.", "días", "liquidez"),
    # fiscal
    "iva_trasladado": ("IVA cobrado en emitidos del mes.", "MXN", "fiscal"),
    "iva_acreditable": ("IVA pagado en recibidos del mes.", "MXN", "fiscal"),
    "iva_neto": ("Trasladado menos acreditable.", "MXN", "fiscal"),
    "isr_estimado": ("Provisión ISR estimada del mes.", "MXN", "fiscal"),
    "pct_gasto_deducible": ("Fracción de egresos conciliables con CFDI.", "tasa", "fiscal"),
    "brecha_pagos_provision": ("Pagos referenciados menos provisión ISR.", "MXN", "fiscal"),
    # comercial CxC
    "cxc_total": ("Total por cobrar abierto.", "MXN", "comercial"),
    "cxc_count": ("Facturas abiertas.", "conteo", "comercial"),
    "cxc_antiguedad_promedio_dias": ("Antigüedad media de CxC.", "días", "comercial"),
    "cxc_pct_vencida": ("Fracción vencida.", "tasa", "comercial"),
    "cxc_top_cliente": ("Participación del mayor cliente en CxC.", "tasa", "comercial"),
    # estructura
    "gasto_por_categoria": ("Gasto por categoría SAT.", "mapa", "estructura"),
    "gasto_por_rubro": ("Gasto por rubro con top1 y hints.", "mapa", "estructura"),
    "margen_bruto_proxy": ("1 menos directos sobre ventas.", "tasa", "estructura"),
    "fondeo_interno": ("Traspasos internos recibidos.", "MXN", "estructura"),
    "ratio_fondeo_interno": ("Fondeo interno entre ventas.", "tasa", "estructura"),
    "hhi_gasto_proveedores": ("Concentración de gasto 0-1.", "índice", "estructura"),
    "masa_salarial_estimada": ("Egresos con NOMINA en descripción.", "MXN", "estructura"),
}


def project_next_month(txns: list[Transaction], cfdis: list[Cfdi],
                       matches: list[Match], anio: int, mes: int,
                       ventana: int = 3) -> dict:
    """Proyección determinista del mes siguiente (run-rate + promedio).

    Método: promedio de ventas/gastos de los últimos `ventana` meses CON
    DATOS (misma base que signals(), para no mezclar fuentes). Sin magia:
    supone que el ritmo se mantiene; lo declara en supuestos.
    Confianza: alta (3+ meses base y volatilidad moderada), media
    (2 meses o volatilidad alta), baja (1 solo mes: es run-rate puro).
    Nunca inventa: con 1 mes lo dice explícitamente.
    """
    base: list[tuple[int, int]] = []
    a, m = anio, mes
    while len(base) < ventana:
        s = signals(txns, cfdis, matches, a, m)
        if s.get("tiene_datos"):
            base.append((a, m))
        m -= 1
        if m == 0:
            a, m = a - 1, 12
        if a < anio - 2:
            break
    pa, pm = (anio, mes + 1) if mes < 12 else (anio + 1, 1)
    if not base:
        return {"month_origen": f"{anio}-{mes:02d}",
                "month_proyectado": f"{pa}-{pm:02d}",
                "ventas": None, "gastos": None, "utilidad": None,
                "metodo": "sin_base",
                "confianza": "ninguna",
                "supuestos": ["el mes origen no tiene datos: sin base"],
                "base_meses": []}
    filas = [signals(txns, cfdis, matches, ba, bm) for ba, bm in base]
    n = len(filas)
    ventas = sum((f["ventas"] for f in filas), CERO) / n
    gastos = sum((f["gastos"] for f in filas), CERO) / n
    vols = [f.get("volatilidad_flujo") for f in filas
            if f.get("volatilidad_flujo") is not None]
    vol_alta = any(v is not None and float(v) > 2 for v in vols)
    if n >= 3 and not vol_alta:
        confianza = "alta"
    elif n >= 2:
        confianza = "media"
    else:
        confianza = "baja"
    supuestos = [
        f"promedio de {n} mes(es) con datos "
        f"({', '.join(f'{ba}-{bm:02d}' for ba, bm in sorted(base))})",
        "se supone ritmo constante: sin cambios de ventas, gastos ni clientes",
    ]
    if n == 1:
        supuestos.append("UN SOLO mes base: es run-rate puro, no tendencia")
    if vol_alta:
        supuestos.append("flujo diario volátil: el rango real puede variar")
    out = {"month_origen": f"{anio}-{mes:02d}",
           "month_proyectado": f"{pa}-{pm:02d}",
           "ventas": ventas, "gastos": gastos, "utilidad": ventas - gastos,
           "metodo": "promedio_ventana" if n > 1 else "run_rate",
           "confianza": confianza, "supuestos": supuestos,
           "base_meses": [f"{ba}-{bm:02d}" for ba, bm in sorted(base)]}
    red = _redondear({k: v for k, v in out.items()
                      if k in ("ventas", "gastos", "utilidad")})
    return {**out, **red}


def metric_catalog() -> list[dict]:
    """Catálogo auto-generado: una entrada por key de signals()."""
    return [{"nombre": k, "descripcion": v[0], "unidad": v[1], "familia": v[2]}
            for k, v in METRIC_CATALOG.items()]
