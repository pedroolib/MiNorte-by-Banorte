"""Tests de reconciliación: curva de scores + bandas + greedy determinista."""

from datetime import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from app.financial import reconcile as rc
from app.schemas.cfdi import Cfdi
from app.schemas.transaction import Transaction

MX = ZoneInfo("America/Mexico_City")


def T(id, fecha, tipo, monto, merchant="PROVEEDOR FICTICIO SA DE CV",
      rfc="PRO010101AA1", cat="tarjeta"):
    return Transaction(
        id=id, company_id="company_001", account_id="acc",
        amount=Decimal(monto), currency="MXN",
        date=datetime(2026, 8, fecha, 12, tzinfo=MX),
        description=f"MOV {id}", merchant_name=merchant, merchant_rfc=rfc,
        type=tipo, source="banorte_mock", categoria=cat,
    )


def C(uuid, total, dia, nombre="PROVEEDOR FICTICIO SA DE CV",
      rfc="PRO010101AA1", tipo="recibido"):
    emisor = ("CNM160812AB1", "CAFE NORTENO SA DE CV") if tipo == "emitido" else (rfc, nombre)
    recep = (rfc, nombre) if tipo == "emitido" else ("CNM160812AB1", "CAFE NORTENO SA DE CV")
    return Cfdi(
        uuid=uuid, company_id="company_001", tipo=tipo,
        emisor_rfc=emisor[0], emisor_nombre=emisor[1],
        receptor_rfc=recep[0], receptor_nombre=recep[1],
        total=Decimal(total), subtotal=Decimal(total) / Decimal("1.16"),
        iva=Decimal(total) - Decimal(total) / Decimal("1.16"),
        fecha_emision=datetime(2026, 8, dia, 12, tzinfo=MX),
        concepto="X",
    )


def test_scores_curvas():
    assert rc.amount_score(Decimal("100"), Decimal("100")) == 1
    # dif relativa 5/105 -> 1 - 0.476 = 11/21
    assert rc.amount_score(Decimal("100"), Decimal("105")) == Decimal(11) / Decimal(21)
    assert rc.amount_score(Decimal("100"), Decimal("120")) == 0  # 16.7% off -> 0
    assert rc.date_score(datetime(2026, 8, 1), datetime(2026, 8, 1)) == 1
    assert rc.date_score(datetime(2026, 8, 1), datetime(2026, 8, 16)) == 0
    assert rc.merchant_score("A", "A") == 1
    assert rc.merchant_score("", "A") == 0
    # sufijos SA DE CV no penalizan
    assert rc.merchant_score("ACME SA DE CV", "ACME") > Decimal("0.9")


def test_pareja_exacta_es_auto():
    t = T("t1", 10, "egreso", "2472.00")
    c = C("u1", "2472.00", 10)
    total, am, fe, co = rc.score(t, c)
    assert total == 1 and am == 1 and fe == 1 and co == 1
    (m,) = rc.conciliar([t], [c])
    assert (m.status, m.cfdi_id) == ("auto", "u1")


def test_banda_review_y_unmatched():
    t = T("t1", 10, "egreso", "2472.00")
    # mismo monto y comercio, 6 días después: 1*0.5 + 0.6*0.2 + 1*0.3 = 0.92 auto
    c1 = C("u1", "2472.00", 16)
    (m1,) = rc.conciliar([t], [c1])
    assert m1.status == "auto" and m1.cfdi_id == "u1"
    # lejos en todo (monto +20%, 14 días, otro comercio) -> unmatched
    c2 = C("u2", "3000.00", 24, nombre="OTRO NEGOCIO DISTINTO SA DE CV",
           rfc="OTR010101XX1")
    (m2,) = rc.conciliar([t], [c2])
    assert m2.status == "unmatched" and m2.cfdi_id is None
    # review: monto 2% off + mismo día + mismo comercio ≈ 0.8*0.5+0.2+0.3 = 0.9? no:
    # 0.8*0.5=0.4 +0.2+0.3=0.9 auto. Para review: monto 5% off mismo día:
    # (1-0.5)*0.5=0.25+0.2+0.3 = 0.75 review
    c3 = C("u3", "2595.60", 10)  # +5%
    (m3,) = rc.conciliar([t], [c3])
    assert m3.status == "review" and m3.cfdi_id == "u3"


def test_greedy_un_cfdi_una_vez_y_determinista():
    t1 = T("t1", 10, "egreso", "100.00")
    t2 = T("t2", 11, "egreso", "100.00")
    c = C("u1", "100.00", 10)
    ms = rc.conciliar([t1, t2], [c])
    auto = [m for m in ms if m.status == "auto"]
    un = [m for m in ms if m.status == "unmatched"]
    assert len(auto) == 1 and len(un) == 1
    assert auto[0].transaction_id == "t1"  # el más cercano en fecha gana
    assert rc.conciliar([t1, t2], [c])[0].transaction_id == "t1"  # determinista


def test_no_conciliables_se_ignoran():
    interno = T("i", 10, "ingreso", "50", cat="traspaso_interno")
    interno.es_interno = True
    comision = T("c", 10, "egreso", "5.00", cat="comision", rfc="BNO1")
    Sin_rfc = T("s", 10, "egreso", "9.00", rfc=None)
    assert rc.conciliar([interno, comision, Sin_rfc], []) == []


def test_cxc_solo_emitidos_sin_cobro():
    cobrada = C("uc", "100.00", 5, tipo="emitido")
    abierta = C("ua", "200.00", 6, tipo="emitido")
    rec = C("ur", "50.00", 6, tipo="recibido")
    t = T("t1", 10, "ingreso", "100.00", merchant="CLIENTE X", cat="spei_recibido")
    ms = rc.conciliar([t], [cobrada, abierta, rec])
    assert [m for m in ms if m.cfdi_id == "uc"]
    recs = rc.detectar_cxc([cobrada, abierta, rec], ms, "company_001")
    assert [r.cfdi_id for r in recs] == ["ua"]
    assert recs[0].amount == Decimal("200.00") and recs[0].status == "open"
    assert (recs[0].due_date - recs[0].issued_at).days == 30
