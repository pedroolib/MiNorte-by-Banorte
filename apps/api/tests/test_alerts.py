"""Tests de reglas del Analista: cada regla dispara y calla cuando debe."""

from datetime import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from app.financial import alerts as al
from app.financial import reconcile as rc
from app.schemas.cfdi import Cfdi
from app.schemas.match import Match
from app.schemas.transaction import Transaction

MX = ZoneInfo("America/Mexico_City")
CID = "company_001"


def T(id, mes, dia, tipo, monto, merchant="PROV", rfc="PRO010101AA1",
      cat="tarjeta", balance=None):
    return Transaction(
        id=id, company_id=CID, account_id="acc", amount=Decimal(monto),
        currency="MXN", date=datetime(2026, mes, dia, 12, tzinfo=MX),
        description=f"MOV {id}", merchant_name=merchant, merchant_rfc=rfc,
        type=tipo, balance=Decimal(balance) if balance else None,
        source="banorte_mock", categoria=cat,
    )


def C(uuid, total, mes, dia, tipo="recibido", nombre="PROV", rfc="PRO010101AA1"):
    em = ("CNM160812AB1", "CAFE") if tipo == "emitido" else (rfc, nombre)
    re = (rfc, nombre) if tipo == "emitido" else ("CNM160812AB1", "CAFE")
    return Cfdi(
        uuid=uuid, company_id=CID, tipo=tipo, emisor_rfc=em[0], emisor_nombre=em[1],
        receptor_rfc=re[0], receptor_nombre=re[1], total=Decimal(total),
        subtotal=Decimal(total) / Decimal("1.16"),
        iva=Decimal(total) - Decimal(total) / Decimal("1.16"),
        fecha_emision=datetime(2026, mes, dia, 12, tzinfo=MX), concepto="X",
    )


def test_sin_factura_y_cxc():
    txns = [
        T("e1", 8, 1, "egreso", "1000", balance="9000"),   # sin CFDI
        T("e2", 8, 2, "egreso", "2000", balance="7000"),   # con CFDI
        T("i1", 8, 3, "ingreso", "5000", merchant="CLI", cat="spei_recibido", balance="12000"),
    ]
    cfdis = [C("u-e2", "2000.00", 8, 2), C("u-i1", "5000.00", 8, 1, tipo="emitido", nombre="CLI", rfc="CLI010101AA1"),
             C("u-cxc", "3000.00", 8, 5, tipo="emitido", nombre="MOROSO", rfc="MOR010101AA1")]
    ms = rc.conciliar(txns, cfdis)
    recs = rc.detectar_cxc(cfdis, ms, CID)
    assert [r.cfdi_id for r in recs] == ["u-cxc"]
    als = al.generar_alertas(txns, cfdis, ms, 2026, 8, CID)
    rules = {a["rule"]: a for a in als}
    assert rules["sin_factura"]["total"] == Decimal("1000")
    assert "1 gasto necesita factura" in rules["sin_factura"]["titulo"]
    assert rules["cuentas_por_cobrar"]["total"] == Decimal("3000")
    assert rules["sin_factura"]["payload"]["component"] == "receipts_resolution"


def test_tendencias_mom():
    # jul: ventas 10k gastos 6k (margen 40%). ago: ventas 10.4k (+4%) gastos 8.8k (+46%)
    txns = [
        T("j1", 7, 1, "ingreso", "10000", cat="spei_recibido", balance="10000"),
        T("j2", 7, 2, "egreso", "6000", balance="4000"),
        T("a1", 8, 1, "ingreso", "10400", cat="spei_recibido", balance="14400"),
        T("a2", 8, 2, "egreso", "8800", balance="5600"),
    ]
    als = al.generar_alertas(txns, [], [], 2026, 8, CID)
    rules = {a["rule"]: a for a in als}
    assert "gasto_vs_ventas" in rules  # 46% - 4% > 10pp
    assert "margen_caida" in rules     # 40% -> 15.4% > 3pp
    assert "Gastos 47%" in rules["gasto_vs_ventas"]["detalle"] or "46%" in rules["gasto_vs_ventas"]["detalle"]


def test_efectivo_bajo_critico_y_silencio():
    # burn 9k/mes, caja 1k -> ~3 días -> critical
    txns = [T("a1", 8, 1, "ingreso", "1000", cat="spei_recibido", balance="10000"),
            T("a2", 8, 2, "egreso", "9000", balance="1000")]
    als = al.generar_alertas(txns, [], [], 2026, 8, CID)
    eb = next(a for a in als if a["rule"] == "efectivo_bajo")
    assert eb["severity"] == "critical" and "~3 días" in eb["titulo"]
    # negocio sano y sin pendientes: sin alertas
    sanos = [T("s1", 8, 1, "ingreso", "10000", cat="spei_recibido", balance="20000"),
             T("s2", 8, 2, "egreso", "5000", balance="15000")]
    ms = rc.conciliar(sanos, [C("u", "5000.00", 8, 2)])
    assert al.generar_alertas(sanos, [C("u", "5000.00", 8, 2)], ms, 2026, 8, CID) == []
