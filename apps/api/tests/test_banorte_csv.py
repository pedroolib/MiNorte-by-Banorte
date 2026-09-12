"""Tests del loader CSV espejo (seed/transactions.csv, 473 movs reales anonimizados)."""

from decimal import Decimal
from pathlib import Path

from app.integrations.banking.banorte_csv import cargar_csv, clasificar

REPO = Path(__file__).resolve().parents[3]
CSV = REPO / "seed" / "transactions.csv"


def test_csv_carga_473():
    txns = cargar_csv(CSV)
    assert len(txns) == 473
    assert all(t.currency == "MXN" for t in txns)
    assert all(t.amount > 0 for t in txns)


def test_totales_mensuales_exactos():
    txns = cargar_csv(CSV)
    # Flujo neto mensual (las devoluciones son retiro negativo = ingreso neto)
    esperado_neto = {
        (2026, 6): "-11876.58",   # 323494.19 - 335370.77
        (2026, 7): "-13941.40",   # 300638.30 - 314579.70
        (2026, 8): "-8437.28",    # 421664.79 - 430102.07
    }
    for (anio, mes), neto_e in esperado_neto.items():
        fm = [t for t in txns if t.date.year == anio and t.date.month == mes]
        neto = sum(
            (t.amount if t.type == "ingreso" else -t.amount for t in fm),
            Decimal("0"),
        )
        assert str(neto) == neto_e, (mes, neto)


def test_cadena_saldos_cierra():
    txns = cargar_csv(CSV)
    previo = None
    for t in txns:
        assert t.balance is not None
        if previo is not None and t.balance != 0:
            delta = t.amount if t.type == "ingreso" else -t.amount
            assert abs((previo + delta) - t.balance) <= Decimal("0.02"), t.id
        previo = t.balance


def test_internos_marcados_y_rfc_upper():
    txns = cargar_csv(CSV)
    internos = [t for t in txns if t.es_interno]
    assert len(internos) == 31
    assert all("TRASPASO INTERNO" in t.description.upper() for t in internos)
    for t in txns:
        if t.merchant_rfc:
            assert t.merchant_rfc == t.merchant_rfc.upper(), t.id


def test_clasificar_casos_reales():
    assert clasificar("TRASPASO A CUENTA DE TERCEROS 0000020123") == "traspaso_terceros"
    assert clasificar("BNET01002301170033990674 SPEI RECIBIDO, BCO:0012") == "spei_recibido"
    assert clasificar("COMPRA ORDEN DE PAGO SPEI 0020123 =REFERENCIA") == "spei_enviado"
    assert clasificar("PAGO REFERENCIADO 546459400623 Impuesto Deposito Referenciado") == "impuestos"
    assert clasificar("PAGO DE LDC-IMSS ALTA: Z1KPHF") == "imss"
    assert clasificar("COMISION ORDEN DE PAGO SPEI REFERENCIA: 1") == "comision"
    assert clasificar("I.V.A. ORDEN DE PAGO SPEI REFERENCIA: 1") == "iva_comision"
    assert clasificar("MERPAGO*MER PAGO 2 RFC:MAG 2105031W3") == "tarjeta"
