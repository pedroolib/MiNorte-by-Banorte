"""Valida contratos + seed provisional T0."""

from decimal import Decimal
from pathlib import Path

from app.schemas.cfdi import Cfdi
from app.schemas.financial import FinancialSummary
from app.schemas.receivable import Receivable
from app.schemas.transaction import Transaction

SEED = Path(__file__).resolve().parents[3] / "seed"


def test_seed_transactions_valid():
    from app.integrations.banking.banorte_csv import cargar_csv
    parsed = cargar_csv(SEED / "transactions.csv")
    assert len(parsed) == 473
    assert all(p.currency == "MXN" for p in parsed)
    assert all(p.amount > 0 for p in parsed)


def test_rfc_uppercase_and_decimal():
    t = Transaction(
        id="txn_x",
        company_id="company_001",
        account_id="acc_eje_001",
        amount=Decimal("100.10"),
        currency="MXN",
        date="2026-08-12T14:30:00-06:00",
        description="OXXO",
        merchant_name="OXXO",
        merchant_rfc="omx140726u5a",
        type="egreso",
    )
    assert t.merchant_rfc == "OMX140726U5A"
    assert isinstance(t.amount, Decimal)


def test_receivable_pending_autocalc():
    r = Receivable(
        id="ar_1",
        company_id="company_001",
        cfdi_id="12345678-1234-1234-1234-123456789012",
        customer_name="Cliente ABC",
        customer_rfc="abc010101abc",
        amount=Decimal("18500"),
        amount_paid=Decimal("0"),
        issued_at="2026-08-12T12:00:00-06:00",
    )
    assert r.amount_pending == Decimal("18500")
    assert r.customer_rfc == "ABC010101ABC"


def test_financial_summary_mock_numbers():
    s = FinancialSummary(
        ventas=Decimal("482300"),
        gastos=Decimal("410900"),
        utilidad=Decimal("71400"),
        efectivo=Decimal("184200"),
        impuesto_estimado=Decimal("32600"),
        cuentas_por_cobrar=Decimal("84500"),
        gastos_sin_cfdi_count=4,
    )
    assert s.utilidad == s.ventas - s.gastos
    assert s.gastos_sin_cfdi_total == Decimal("0")


def test_cfdi_rfc_upper():
    c = Cfdi(
        uuid="12345678-1234-1234-1234-123456789012",
        company_id="company_001",
        tipo="emitido",
        emisor_rfc="cnm160812ab1",
        emisor_nombre="CAFE NORTENO SA DE CV",
        receptor_rfc="abc010101abc",
        receptor_nombre="CLIENTE ABC",
        total=Decimal("18500"),
        subtotal=Decimal("15948.28"),
        iva=Decimal("2551.72"),
        fecha_emision="2026-08-12T12:00:00-06:00",
        concepto="Venta mostrador",
    )
    assert c.emisor_rfc == "CNM160812AB1"
