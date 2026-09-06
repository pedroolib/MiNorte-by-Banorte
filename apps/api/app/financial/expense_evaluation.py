"""Evaluación genérica de gastos (una sola matemática para infinitos gastos).

El modelo detecta el tipo, lee el checklist, pregunta faltantes y compone
la llamada. ESTE módulo valida, calcula y dictamina. Nunca adivina:
lo que falta se devuelve como error `falta: [...]` para repreguntar.

Base de capacidad: caja bancaria del mes (consistente con el dashboard),
más contexto operativo y advertencia de fondeo interno. Todo etiquetado.
"""

from __future__ import annotations

import re
from datetime import date
from decimal import Decimal

from app.financial import engine as en
from app.financial.expense_profiles import get_profile
from app.schemas.transaction import Transaction

CERO = Decimal("0")
CENT = Decimal("0.01")


def _money(raw: str, nombre: str) -> Decimal:
    s = (raw or "").strip().replace("$", "").replace(",", "").replace(" ", "")
    if not re.fullmatch(r"-?\d+(\.\d{1,2})?", s):
        raise ValueError(f"{nombre}: monto inválido {raw!r} (usa 25000.00)")
    v = Decimal(s).quantize(CENT)
    if v < 0:
        raise ValueError(f"{nombre}: no acepta negativos")
    return v


class FaltaDato(ValueError):
    """Error estructurado: lo que falta + cómo preguntarlo."""


def _money(raw: str, nombre: str) -> Decimal:
    s = (raw or "").strip().replace("$", "").replace(",", "").replace(" ", "")
    if not re.fullmatch(r"-?\d+(\.\d{1,2})?", s):
        raise ValueError(f"{nombre}: monto inválido {raw!r} (usa 25000.00)")
    v = Decimal(s).quantize(CENT)
    if v < 0:
        raise ValueError(f"{nombre}: no acepta negativos")
    return v


def _percent(raw: str, nombre: str) -> Decimal:
    s = (raw or "").strip().replace(" ", "")
    tiene_pct = s.endswith("%")
    s = s[:-1] if tiene_pct else s
    try:
        v = Decimal(s)
    except Exception:
        raise ValueError(f"{nombre}: porcentaje inválido {raw!r}")
    if v < 0:
        raise ValueError(f"{nombre}: no acepta negativos")
    # "30"/"30%" -> 0.30 ; "0.30" -> 0.30
    return (v / 100).quantize(Decimal("0.0001")) if (tiene_pct or v > 1) else v


def _int(raw: str, nombre: str, minimo: int = 1) -> int:
    s = (raw or "").strip()
    if not re.fullmatch(r"\d+", s) or int(s) < minimo:
        raise ValueError(f"{nombre}: entero >= {minimo}, llegó {raw!r}")
    return int(s)


def _enum(raw: str, nombre: str, opciones: list[str]) -> str:
    v = (raw or "").strip().lower()
    if v not in opciones:
        raise ValueError(f"{nombre}: debe ser uno de {opciones}, llegó {raw!r}")
    return v


def _parse_var(spec: dict, valor: str, unidad: str):
    tipo = spec["tipo"]
    unidad = (unidad or "").strip()
    if tipo == "money":
        if unidad not in ("", "MXN", "$"):
            raise ValueError(f"{spec['nombre']}: unidad {unidad!r} no válida (MXN)")
        return _money(valor, spec["nombre"])
    if tipo == "percent":
        if unidad not in ("", "%"):
            raise ValueError(f"{spec['nombre']}: unidad {unidad!r} no válida (%)")
        return _percent(valor, spec["nombre"])
    if tipo == "rate":
        if unidad not in ("", "%"):
            raise ValueError(f"{spec['nombre']}: unidad {unidad!r} no válida (%)")
        return _percent(valor, spec["nombre"])
    if tipo == "int":
        if unidad not in ("", "meses", "mes"):
            raise ValueError(f"{spec['nombre']}: unidad {unidad!r} no válida (meses)")
        return _int(valor, spec["nombre"])
    if tipo == "enum":
        return _enum(valor, spec["nombre"], spec["opciones"])
    raise ValueError(f"tipo desconocido: {tipo}")


def _tasa_mensual(tasa_anual: Decimal | None, cat_anual: Decimal | None,
                  supuestos: list) -> Decimal:
    if (tasa_anual is None) == (cat_anual is None):
        raise FaltaDato("tasa_anual XOR cat_anual (una de las dos)")
    if cat_anual is not None:
        supuestos.append("CAT usada como tasa efectiva anual (aproximación; "
                         "el CAT real incluye seguros/comisiones de cada institución).")
        return ((CERO + 1 + cat_anual).ln() / 12).exp() - 1
    return tasa_anual / 12


def tomar_default(spec: dict, supuestos: list):
    """Aplica un default registrando el supuesto. None = se resuelve fuera."""
    d = spec["default"]
    nota = (spec.get("default_nota") or "").strip()
    if d == "one_month_rent":
        return None
    if spec["tipo"] == "enum":
        supuestos.append(f"{spec['nombre']}={d} ({nota})".strip())
        return d
    if spec["tipo"] == "percent":
        supuestos.append(f"{spec['nombre']}={float(Decimal(d)) * 100:.0f}% ({nota})".strip())
        return Decimal(d)
    if spec["tipo"] == "int":
        supuestos.append(f"{spec['nombre']}={d} ({nota})".strip())
        return int(d)
    supuestos.append(f"{spec['nombre']}={d} ({nota})".strip())
    return Decimal(d)


def variables_checklist(expense_type: str | None = None) -> dict:
    """Checklist para el modelo (y para UI futura). Sin cálculos."""
    from app.financial.expense_profiles import EXPENSE_PROFILES, list_expense_types

    if not expense_type:
        return {"tipos": list_expense_types(),
                "uso": "elige tipo, luego pide su checklist con get_variables_gasto(tipo)"}
    p = get_profile(expense_type)
    return {"tipo": expense_type, "label": p["label"],
            "variables": p["variables"],
            "requerido_uno_de": p.get("requerido_uno_de", []),
            "nota": "máximo 2 rondas de preguntas; solo faltantes; defaults declarados"}


def evaluar_gasto(txns: list[Transaction], expense_type: str,
                  variables: list[dict], month: str | None = None,
                  horizon_months: int | None = None,
                  etapas: list[dict] | None = None) -> dict:
    """Valida, calcula y dictamina. Faltantes -> FaltaDato (repreguntar)."""
    from app import data as _data

    perfil = get_profile(expense_type)
    specs = {v["nombre"]: v for v in perfil["variables"]}
    dados: dict[str, dict] = {}
    for item in variables or []:
        nombre = item.get("nombre", "")
        if nombre not in specs:
            raise FaltaDato(
                f"variable desconocida: {nombre!r}; válidas: {sorted(specs)}")
        dados[nombre] = item
    vals: dict = {}
    supuestos: list[str] = []

    # 1. parsear lo dado; rechazar nombres desconocidos (sin ruteo silencioso)
    resueltos: dict = {}
    for v in perfil["variables"]:
        if v["nombre"] in dados:
            try:
                resueltos[v["nombre"]] = _parse_var(
                    v, dados[v["nombre"]].get("valor", ""),
                    dados[v["nombre"]].get("unidad", ""))
            except ValueError as e:
                raise FaltaDato(str(e))

    def _aplica(v) -> bool:
        cond = v.get("requerido_si")
        if not cond:
            return True
        actual = resueltos.get(cond["campo"])
        if actual is None:
            ref = specs[cond["campo"]]
            if "default" in ref:
                actual = tomar_default(ref, supuestos)
            else:
                return False
        return actual == cond["es"]

    # 2. defaults (siempre declarados en supuestos)
    for v in perfil["variables"]:
        if v["nombre"] in resueltos or "default" not in v:
            continue
        if v.get("requerido_si") and not _aplica(v):
            continue
        d = tomar_default(v, supuestos)
        if d is not None:
            resueltos[v["nombre"]] = d

    # 3. requeridos simples, condicionales y grupos uno-de
    faltantes: list[str] = []
    for v in perfil["variables"]:
        if v["nombre"] in resueltos:
            continue
        if v.get("requerido") or (v.get("requerido_si") and _aplica(v)):
            faltantes.append(v["nombre"])
    alternativas = perfil.get("requerido_uno_de", [])
    if alternativas and not any(all(g in resueltos for g in alt) for alt in alternativas):
        faltantes.append("uno de: " + " o ".join(
            "+".join(alt) for alt in alternativas))
    if faltantes:
        preguntas = [specs[n]["pregunta"] for n in faltantes if n in specs]
        raise FaltaDato("falta: " + ", ".join(faltantes)
                        + ". Pregunta: " + " ".join(preguntas))

    # 2. mes y horizonte
    if month:
        anio, mes = map(int, month.split("-"))
    else:
        ult = max(t.date for t in txns)
        anio, mes = ult.year, ult.month
    financing_months = 0
    for k in ("months", "contract_months", "term_months", "duration_months"):
        if isinstance(resueltos.get(k), int):
            financing_months = max(financing_months, resueltos[k])
    horizonte = horizon_months or max(12, financing_months)
    horizonte = max(1, min(int(horizonte), 60))

    # 3. baseline operativa explícita (sin traspasos internos, igual que
    # dashboard/snapshots; el fondeo interno se reporta aparte, no como venta)
    fm = [t for t in txns if (t.date.year, t.date.month) == (anio, mes)]
    dep = sum((t.amount for t in fm if t.type == "ingreso" and not t.es_interno), CERO)
    ret = sum((t.amount for t in fm if t.type == "egreso" and not t.es_interno), CERO)
    utilidad_bank = dep - ret
    burn = -min((dep - ret), CERO)
    ordenados = sorted(txns, key=lambda t: (t.date, t.id))
    efectivo = ordenados[-1].balance or CERO
    dep_int = sum((t.amount for t in fm if t.type == "ingreso" and t.es_interno), CERO)
    fondeo = (dep_int / dep) if dep > 0 else CERO
    inc_op = en.income_statement(txns, anio, mes)["utilidad"]
    baseline = {"fuente": "caja_operativa", "utilidad": utilidad_bank,
                "burn_mensual": burn, "efectivo": efectivo,
                "utilidad_operativa": inc_op, "fondeo_interno_ratio": fondeo}
    if fondeo > Decimal("0.5"):
        baseline["advertencia"] = (
            f"cuenta fondeada {float(fondeo) * 100:.0f}% con traspasos internos; "
            "la capacidad real depende de las otras cuentas")

    # 4. flujos por tipo
    R = resueltos
    financiamiento = None
    initial = CERO
    mensuales: list[Decimal] = [CERO] * horizonte
    ingresos_m: list[Decimal] = [CERO] * horizonte

    def _financiar(principal: Decimal, etiqueta: str):
        nonlocal initial
        tasa = R.get("tasa_anual")
        cat = R.get("cat_anual")
        if tasa is None and cat is None:
            raise FaltaDato("falta: tasa_anual o cat_anual. "
                            "Pregunta: ¿Qué tasa anual nominal o qué CAT?")
        for extra in ("comision_apertura", "seguro_mensual", "monthly_insurance"):
            if extra in R and R[extra]:
                raise FaltaDato(
                    f"con CAT no desgloses {extra}: usa CAT *o* tasa + desglose, no ambos")
        n = R.get("months")
        if n is None:
            raise FaltaDato("falta: months. Pregunta: ¿A cuántos meses?")
        rm = _tasa_mensual(tasa, cat, supuestos)
        pago = en.amortizar_francesa(principal, rm, int(n))
        return {"principal": principal, "tasa_mensual_efectiva": rm,
                "pago_mensual": pago,
                "total_intereses": pago * int(n) - principal,
                "plazo_meses": int(n),
                "con_cat": cat is not None}

    if expense_type == "empleado":
        costo = R.get("monthly_cost_total")
        if costo is None:
            costo = (R["salary_base"] * (CERO + 1 + R.get("benefits_pct", CERO)))
        mensuales = [costo] * horizonte
    elif expense_type == "mercancia":
        initial = R["purchase_cost"]
        total_rev = R.get("expected_revenue") or (
            R["purchase_cost"] * (CERO + 1 + R["expected_margin_pct"]))
        n = R.get("months_to_sell", 3)
        for i in range(min(int(n), horizonte)):
            ingresos_m[i] = (total_rev / int(n)).quantize(CENT)
    elif expense_type in ("auto", "terreno", "maquinaria"):
        precio = R["price"]
        mod = R.get("payment_modality", "contado")
        rec = R.get("monthly_insurance", CERO) + R.get("monthly_fuel_maintenance", CERO) \
            + R.get("monthly_costs", CERO) + R.get("monthly_maintenance", CERO)
        ben = R.get("monthly_benefit", CERO)
        if mod == "contado":
            initial = precio
            mensuales = [rec] * horizonte
            ingresos_m = [ben] * horizonte
        else:
            down = R.get("down_payment")
            if down is None:
                down = (precio * R.get("down_payment_pct", Decimal("0.20"))).quantize(CENT)
                supuestos.append("enganche 20% del precio.")
            fin = _financiar(precio - down, expense_type)
            financiamiento = fin
            initial = down
            mensuales = [fin["pago_mensual"] + rec] * horizonte
            ingresos_m = [ben] * horizonte
    elif expense_type == "construccion":
        total = R["total_budget"]
        dur = int(R["duration_months"])
        upfront = R.get("upfront_amount", CERO)
        if etapas:
            draw = [CERO] * horizonte
            for e in etapas:
                try:
                    mes_i = int(e.get("mes", 0))
                    monto = _money(str(e.get("monto", "")), "etapa.monto")
                except ValueError as ex:
                    raise FaltaDato(f"etapa inválida: {ex}")
                if not 1 <= mes_i <= dur:
                    raise FaltaDato(f"etapa fuera de duración 1..{dur}: mes {mes_i}")
                if mes_i <= horizonte:
                    draw[mes_i - 1] += monto
            mensuales = draw
        else:
            supuestos.append("ministraciones lineales (sin etapas detalladas).")
            mensuales = [((total - upfront) / dur).quantize(CENT)] * min(dur, horizonte) + \
                        [CERO] * max(0, horizonte - dur)
        initial = upfront
    elif expense_type == "renta":
        renta = R["monthly_rent"]
        plazo = int(R.get("term_months", 12))
        inc = R.get("annual_increase_pct", CERO)
        initial = R.get("deposit", renta)
        if "deposit" not in R:
            supuestos.append("depósito = 1 mes de renta.")
        for i in range(min(plazo, horizonte)):
            mensuales[i] = (renta * ((CERO + 1 + inc) ** (i // 12))).quantize(CENT)
    else:
        raise FaltaDato(f"tipo no soportado: {expense_type}")

    netos = [c - i for c, i in zip(mensuales, ingresos_m)]
    monthly_max = max(netos) if netos else CERO

    # 5. veredicto unificado
    if initial > efectivo:
        veredicto, motivo = "no_viable", "el desembolso supera el efectivo disponible"
    elif monthly_max <= 0:
        veredicto, motivo = "viable", "se paga solo en el horizonte"
    else:
        cobertura = (utilidad_bank / monthly_max) if utilidad_bank > 0 else CERO
        burn_nuevo = burn + monthly_max
        runway = int(efectivo / (burn_nuevo / 30)) if burn_nuevo > 0 else None
        if cobertura >= Decimal("1.5"):
            veredicto, motivo = "viable", f"cubre {float(cobertura):.1f}x la utilidad"
        elif cobertura >= 1:
            veredicto, motivo = "ajustada", "cubre justo la utilidad"
        elif runway is not None and runway >= 90:
            veredicto, motivo = "riesgosa", f"no cubre con utilidad pero hay {runway} días"
        else:
            veredicto, motivo = "no_viable", "no cubre y el colchón es corto"
    return {
        "expense_type": expense_type, "month": f"{anio}-{mes:02d}",
        "horizon_months": horizonte, "baseline": baseline,
        "supuestos": supuestos, "initial_outlay": initial,
        "monthly_max": monthly_max,
        "monthly_income_total": sum(ingresos_m, CERO),
        "cash_flows": [{"mes": i + 1, "flujo": -(netos[i])} for i in range(horizonte)],
        "financiamiento": financiamiento,
        "cobertura": (utilidad_bank / monthly_max) if (monthly_max > 0 and utilidad_bank > 0) else CERO,
        "runway_dias": int(efectivo / ((burn + monthly_max) / 30)) if (burn + monthly_max) > 0 else None,
        "veredicto": veredicto, "motivo": motivo,
    }
