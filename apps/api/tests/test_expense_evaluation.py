"""Evaluador genérico: validación, defaults declarados, matemática exacta."""

from datetime import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest

from app.financial import engine as en
from app.financial.expense_evaluation import FaltaDato, evaluar_gasto, variables_checklist
from app.financial.expense_profiles import EXPENSE_PROFILES
from app.schemas.transaction import Transaction

MX = ZoneInfo("America/Mexico_City")


def T(id, dia, tipo, monto, categoria="tarjeta", interno=False, balance=None):
    return Transaction(
        id=id, company_id="company_001", account_id="acc",
        amount=Decimal(monto), currency="MXN",
        date=datetime(2026, 7 if dia < 100 else 8, dia % 100, 12, tzinfo=MX),
        description=f"MOV {id}", merchant_name="M", type=tipo,
        balance=Decimal(balance) if balance else None,
        source="banorte_mock", es_interno=interno, categoria=categoria,
    )


def fixture():
    return [
        T("j1", 5, "ingreso", "10000", categoria="spei_recibido", balance="10000"),
        T("j2", 6, "egreso", "6000", balance="4000"),
        T("j3", 7, "egreso", "1000", interno=True, balance="4000"),
        T("a1", 105, "ingreso", "12000", categoria="spei_recibido", balance="16000"),
        T("a2", 106, "egreso", "9000", balance="7000"),
    ]


def V(**kvs):
    return [{"nombre": k, "valor": str(v), "unidad": u} for k, (v, u) in kvs.items()]


def test_catalogo_siete_tipos():
    assert set(EXPENSE_PROFILES) == {"empleado", "mercancia", "auto", "terreno",
                                     "construccion", "renta", "maquinaria"}
    with pytest.raises(ValueError, match="válidos"):
        variables_checklist("cohete")
    assert variables_checklist(None)["tipos"][0]["tipo"] == "empleado"


def test_empleado_viable_y_no_viable():
    r = evaluar_gasto(fixture(), "empleado",
                      V(monthly_cost_total=("2000", "MXN")), month="2026-07")
    assert r["veredicto"] == "viable" and r["monthly_max"] == Decimal("2000")
    # baseline bancaria julio: utilidad 10000-7000=3000
    assert r["baseline"]["fuente"] == "caja_bancaria"
    assert r["baseline"]["utilidad"] == Decimal("3000")
    r2 = evaluar_gasto(fixture(), "empleado",
                       V(monthly_cost_total=("20000", "MXN")), month="2026-07")
    assert r2["veredicto"] == "no_viable"


def test_empleado_temporal_pide_meses_y_default_prestaciones():
    with pytest.raises(FaltaDato, match="contract_months"):
        evaluar_gasto(fixture(), "empleado",
                      V(salary_base=("10000", "MXN"),
                        contract_type=("temporal", "")), month="2026-07")
    r = evaluar_gasto(fixture(), "empleado",
                      V(salary_base=("10000", "MXN")), month="2026-07")
    assert r["monthly_max"] == Decimal("13000.00")  # base + 30% default
    assert any("30%" in s for s in r["supuestos"])


def test_cat_vs_nominal_y_conflicto():
    vars_cat = V(price=("120000", "MXN"), payment_modality=("financiado", ""),
                cat_anual=("20", "%"), months=("12", "meses"))
    r = evaluar_gasto(fixture(), "auto", vars_cat, month="2026-07")
    assert any("CAT" in s for s in r["supuestos"])
    assert r["financiamiento"]["con_cat"] is True
    vars_mix = vars_cat + [{"nombre": "monthly_insurance", "valor": "500", "unidad": "MXN"}]
    with pytest.raises(FaltaDato, match="CAT.*desglose|desglose.*CAT"):
        evaluar_gasto(fixture(), "auto", vars_mix, month="2026-07")


def test_amortizar_francesa_exacta():
    assert en.amortizar_francesa(Decimal("400000"), Decimal("0.02"), 12) == Decimal("37823.84")
    assert en.amortizar_francesa(Decimal("12000"), Decimal("0"), 12) == Decimal("1000.00")


def test_renta_defaults_declarados():
    r = evaluar_gasto(fixture(), "renta",
                      V(monthly_rent=("5000", "MXN")), month="2026-07")
    assert r["initial_outlay"] == Decimal("5000")  # depósito = 1 mes
    assert any("1 mes de renta" in s for s in r["supuestos"])
    assert len(r["cash_flows"]) == 12


def test_variable_desconocida_se_rechaza():
    with pytest.raises(FaltaDato, match="desconocida"):
        evaluar_gasto(fixture(), "renta",
                      V(monthly_rent=("5000", "MXN"), color_favorito=("azul", "")),
                      month="2026-07")
