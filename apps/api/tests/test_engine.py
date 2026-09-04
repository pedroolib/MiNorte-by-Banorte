"""Tests del Financial Engine con números calculados a mano."""

from datetime import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from app.financial import engine as en
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
        T("j3", 7, "egreso", "1000", interno=True, balance="4000"),  # interno: fuera de P&L
        T("a1", 105, "ingreso", "12000", categoria="spei_recibido", balance="16000"),
        T("a2", 106, "egreso", "9000", balance="7000"),
    ]


def test_income_excluye_internos():
    inc = en.income_statement(fixture(), 2026, 7)
    assert inc["ventas"] == Decimal("10000")
    assert inc["gastos"] == Decimal("6000")
    assert inc["utilidad"] == Decimal("4000")
    assert inc["margen"] == Decimal("0.4")


def test_cash_flow_incluye_todo():
    cf = en.cash_flow(fixture(), 2026, 7)
    assert cf["entradas"] == Decimal("10000")
    assert cf["salidas"] == Decimal("7000")  # 6000 + 1000 interno
    assert cf["neto"] == Decimal("3000")


def test_mom_y_metrics():
    m = en.metrics(fixture(), 2026, 8)
    assert m["crec_ventas"] == Decimal("0.2")   # 10k -> 12k
    assert m["crec_gastos"] == Decimal("0.5")   # 6k -> 9k
    assert m["margen"] == Decimal("0.25")       # 3k/12k
    assert m["margen_previo"] == Decimal("0.4")


def test_mom_sin_base():
    assert en.mom(Decimal("0"), Decimal("5")) is None


def test_taxes_provision_y_pagado():
    txns = fixture() + [T("a3", 107, "egreso", "500", categoria="impuestos")]
    t = en.estimate_taxes(txns, 2026, 8)
    # utilidad ago = 12000 - (9000+500) = 2500 -> ISR 750
    assert t["provision_isr"] == Decimal("750.00")
    assert t["pagos_referenciados"] == Decimal("500")
    assert en.estimate_taxes(fixture(), 2026, 7)["provision_isr"] == Decimal("1200.00")


def test_simulate_hiring_veredictos():
    r = en.simulate_hiring(fixture(), 2026, 7, Decimal("20000"))
    assert r["cubre_con_utilidad"] is False
    assert r["veredicto"] == "no_viable"  # burn 0? neto +3000 -> burn 0 + 20000
    r2 = en.simulate_hiring(fixture(), 2026, 7, Decimal("3000"))
    assert r2["cubre_con_utilidad"] is True and r2["veredicto"] == "viable"


def test_simulate_loan_francesa():
    r = en.simulate_loan(Decimal("30000"), Decimal("400000"), Decimal("0.24"), 12)
    # 400000*0.02/(1-1.02^-12) = 37,823.84 (amortización francesa exacta)
    assert r["pago_mensual"] == Decimal("37823.84")
    assert r["veredicto"] == "no_viable"  # cobertura 0.79 < 1
    r2 = en.simulate_loan(Decimal("100000"), Decimal("400000"), Decimal("0.24"), 12)
    assert r2["veredicto"] == "viable"
