"""Tests del parser Banorte (fixture ficticia + golden test local).

El golden test usa los PDFs reales en seed/private/ (gitignored, con PII)
y se salta en CI. La fixture es 100% ficticia y corre en todos lados.
"""

from decimal import Decimal
from datetime import date
from pathlib import Path

import pytest

from app.integrations.banking import banorte_pdf as bp

REPO = Path(__file__).resolve().parents[3]
PRIVATE = REPO / "seed" / "private"


def fila(fecha: str, desc: str, dep=None, ret=None, saldo=None) -> str:
    """Arma una línea con la grilla real: dep→x124, ret→x150, saldo→x173."""
    base = f" {fecha} {desc}"
    cols = []
    if dep is not None:
        cols.append((124, dep))
    if ret is not None:
        cols.append((150, ret))
    if saldo is not None:
        cols.append((173, saldo))
    linea = base
    for x, monto in cols:
        linea = linea.ljust(x - len(monto)) + monto
    return linea


CAB = (
    " FECHA DESCRIPCIÓN / ESTABLECIMIENTO"
    + " " * 61 + "MONTO DEL DEPOSITO       MONTO DEL RETIRO                   SALDO"
)
DET = "DETALLE DE MOVIMIENTOS (PESOS)"
FIN = "Línea Directa para su empresa:"


def texto(*lineas: str) -> str:
    return "\n".join([DET, CAB, *lineas, FIN])


def test_basico_y_cadena():
    t = texto(
        fila("31-MAY-26", "SALDO ANTERIOR", saldo="10,000.00"),
        fila("01-JUN-26", "SPEI RECIBIDO CLIENTE FICTICIO", dep="60,000.00", saldo="70,000.00"),
        fila("01-JUN-26", "COMPRA PROVEEDOR FICTICIO", ret="5,000.00", saldo="65,000.00"),
        fila("01-JUN-26", "COMISION ORDEN DE PAGO SPEI", ret="5.00", saldo="64,995.00"),
        fila("01-JUN-26", "I.V.A. ORDEN DE PAGO SPEI", ret="0.80", saldo="64,994.20"),
    )
    movs = bp.parsear_texto(t)
    assert len(movs) == 5
    assert bp.validar_cadena(movs) == []
    dep, ret = bp.totales(movs)
    assert dep == Decimal("60000.00")
    assert ret == Decimal("5005.80")
    assert movs[0].es_saldo_anterior


def test_saldo_en_linea_siguiente_y_fecha_pegada():
    t = texto(
        fila("31-MAY-26", "SALDO ANTERIOR", saldo="1,000.00"),
        " 01-JUN-26COMPRA SIN DETALLE",
        " " * 140 + "2,457.44",
        " " * 160 + "500.00",  # x=165+5? -> saldo (>=158)
    )
    movs = bp.parsear_texto(t)
    assert len(movs) == 2
    assert movs[1].retiro == Decimal("2457.44")
    assert movs[1].saldo == Decimal("500.00")
    # 1000 - 2457.44 != 500 -> la cadena debe quejarse (números inventados)
    assert len(bp.validar_cadena(movs)) == 1


def test_devolucion_con_signo_e_informativo_ignorado():
    t = texto(
        fila("31-MAY-26", "SALDO ANTERIOR", saldo="5,000.00"),
        fila("01-JUN-26", "DEV.SPEI MOT DEV:G", ret="699.88-", saldo="5,699.88"),
    )
    movs = bp.parsear_texto(t)
    assert movs[1].retiro == Decimal("-699.88")
    assert bp.validar_cadena(movs) == []

    t2 = texto(
        fila("31-MAY-26", "SALDO ANTERIOR", saldo="10,000.00"),
        fila("01-JUN-26", "COMPRA ORDEN DE PAGO SPEI 001 =REF X", ret="285.08", saldo="9,714.92"),
        "           CVE RASTREO: 8846APR1202301022069498286 RFC: AAA010101AAA IVA: 000000000039.32",
        "           BBVA BANCOMER HORA LIQ: 12:57:19",
    )
    movs2 = bp.parsear_texto(t2)
    assert len(movs2) == 2
    assert movs2[1].retiro == Decimal("285.08")  # el IVA informativo no suma
    assert bp.validar_cadena(movs2) == []


def test_partir_periodos_y_filtro_cuentas():
    t = texto(
        fila("31-MAY-26", "SALDO ANTERIOR", saldo="1.00"),
        fila("01-JUN-26", "COMPRA A", ret="1.00", saldo="0.00"),
        fila("30-JUN-26", "SALDO ANTERIOR", saldo="0.00"),
        fila("01-JUL-26", "COMPRA B", ret="0.00", saldo="0.00"),
    )
    movs = bp.parsear_texto(t)
    periodos = bp.partir_periodos(movs)
    assert len(periodos) == 2
    assert len(periodos[0]) == 2


def test_resolver_ambiguos_por_cadena():
    # importe fuera de columnas (como tiempo aire "$100.00" inline)
    m0 = bp.Movimiento(
        fecha=date(2026, 6, 1), descripcion="x",
        saldo=Decimal("1000"), es_saldo_anterior=True,
    )
    m1 = bp.Movimiento(
        fecha=date(2026, 6, 2), descripcion="tiempo aire",
        saldo=Decimal("900"), candidatos=[Decimal("100")],
    )
    assert bp.resolver_ambiguos([m0, m1]) == 1
    assert m1.retiro == Decimal("100")
    assert bp.validar_cadena([m0, m1]) == []


REAL = PRIVATE / "enlace_versatil_2023.pdf"
PFAE = PRIVATE / "pfae_2025.pdf"


@pytest.mark.skipif(not REAL.exists(), reason="PDF real no disponible (PII local)")
def test_golden_enlace_totales_resumen():
    """Los depósitos parseados deben cuadrar al centavo con el RESUMEN."""
    movs = bp.parsear_texto(bp.extraer_texto(REAL), cuentas={"0211807410"})
    bp.resolver_ambiguos(movs)
    assert bp.validar_cadena(movs) == []
    esperados = {
        1: ("323494.19", "35549.94", "23673.36"),
        2: ("300638.30", "23673.36", "9731.96"),
        3: ("421664.79", "9731.96", "1294.68"),
        4: ("578000.00", "1294.68", "9908.34"),
        5: ("161477.17", "9908.34", "10786.80"),
    }
    periodos = [p for p in bp.partir_periodos(movs) if len(p) > 1]
    assert len(periodos) == 5
    for p in periodos:
        dep, _ = bp.totales(p)
        mes = p[-1].fecha.month
        assert str(dep) == esperados[mes][0], f"mes {mes}"
        assert str(p[0].saldo) == esperados[mes][1]
        assert str(p[-1].saldo) == esperados[mes][2]


@pytest.mark.skipif(not PFAE.exists(), reason="PDF real no disponible (PII local)")
def test_golden_pfae_exacta():
    movs = bp.parsear_texto(bp.extraer_texto(PFAE), cuentas={"1153065849"})
    bp.resolver_ambiguos(movs)
    assert bp.validar_cadena(movs) == []
    dep, ret = bp.totales(movs)
    assert str(dep) == "452168.35"
    # retiros + comisiones (140) + IVA (22.40) que el banco reporta aparte
    assert str(ret) == "453797.92"
