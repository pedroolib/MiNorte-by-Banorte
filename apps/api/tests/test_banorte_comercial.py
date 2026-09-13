"""Parser Banorte: categorías, extracción y reglas por fuente (strings ficticios)."""

from decimal import Decimal

from app.financial import reconcile as rc
from app.integrations.banking import banorte_comercial_pdf as bcom
from app.schemas.transaction import Transaction


def fila(fecha: str, desc: str, monto: str | None, col: int) -> str:
    base = f" {fecha}   {fecha} {desc}"
    if monto is None:
        return base
    return base.ljust(col - len(monto)) + monto


CAB = ("  FECHA DESCRIPCIÓN / X" + " " * 60 + "CARGOS ABONOS SALDO"
       .replace("CARGOS", " " * 61 + "CARGOS"))
DET = "Detalle de Movimientos Realizados"
FIN = "BBVA MEXICO, S.A."


def test_clasificar_banorte():
    C = bcom.clasificar_banorte
    assert C("SPEI ENVIADO BANORTE 123") == ("spei_enviado", False)
    assert C("SPEI RECIBIDOBANAMEX 123") == ("spei_recibido", False)
    assert C("PAGO CUENTA DE TERCERO 123") == ("traspaso_terceros", False)
    assert C("PAGO TARJETA DE CREDITO 123") == ("pago_tdc", True)
    assert C("PAGO INTERBANCARIO TDC 123") == ("pago_tdc", True)
    assert C("VENTAS DEBITO 123") == ("ventas_tpv", False)
    assert C("COM VTAS TDC INTER 123") == ("comision", False)
    assert C("APLI TASA DE DES DEBITO 123") == ("comision", False)
    assert C("CHEQUE PAGADO NO. 123") == ("cheque", False)
    assert C("TRASPADO ENTRE CUENTAS 123") == ("traspaso_interno", True)
    assert C("GOBIERNO DEL ESTADO 123") == ("impuestos", False)
    assert C("COMPRA REFACCIONES NOMINA SEM 123") == ("nomina", False)
    assert C("GONHERMEX,SA DE CV 1.00 GUIA:1 REF:2 CIE:3") == ("spei_enviado", False)
    assert C("DEPOSITO DE TERCERO 1.00 PAGO BMRCASH") == ("deposito_tercero", False)


def test_extraccion_y_materializacion():
    r1 = fila("01/JUL", "SPEI ENVIADO BANORTE", "1,946.99", 100)
    d1 = "0026425627 072 PAGO FACTURAS BALATAS"
    d2 = "LUIS MACIAS SEGURA"
    t = "\n".join([DET, "  FECHA X", r1, d1, d2, FIN])
    movs = bcom.parsear_texto(t, 2026)
    assert len(movs) == 1
    m = movs[0]
    assert m.retiro == Decimal("1946.99") and m.deposito == 0
    assert m.comercio == "Luis Macias Segura"
    assert m.fecha_oper.month == 7


def test_conciliable_por_fuente():
    def T(**kw):
        base = dict(id="x", company_id="c", account_id="a", amount=Decimal("1"),
                    currency="MXN", date="2026-07-01T12:00:00-06:00",
                    description="d", merchant_name="PROVEEDOR REAL",
                    type="egreso", source="banorte_mock", categoria="tarjeta")
        base.update(kw)
        return Transaction(**base)

    # banorte: manda el RFC (comportamiento intacto)
    assert rc.es_conciliable(T(merchant_rfc="AAA010101AAA")) is True
    assert rc.es_conciliable(T(merchant_rfc=None)) is False
    # banorte-comercial: manda el nombre (sin RFCs en el formato)
    b = dict(source="banorte_comercial", merchant_rfc=None)
    assert rc.es_conciliable(T(**b)) is True
    assert rc.es_conciliable(T(**b, merchant_name="VENTAS TPV")) is False
    assert rc.es_conciliable(T(**b, merchant_name="AB")) is False
    assert rc.es_conciliable(T(**b, merchant_name="COMPRA ORDEN DE PAGO SPEI 1")) is False
