"""Invariantes del seed CFDI (pareo banco <-> XMLs).

Reglas que T5 asume:
- todo RECIBIDO calza con un retiro bancario (mismo total),
- todo EMITIDO salvo 5 calza con un depósito (cobro),
- los 5 impagados suman $76,550.00 (CxC demo con montos realistas),
- exactamente 4 egresos con RFC quedan sin XML (alerta Resolver).
"""

import csv
from decimal import Decimal
from pathlib import Path

from app.integrations.sat import cfdi_xml as cx

REPO = Path(__file__).resolve().parents[3]
DIR = REPO / "seed" / "cfdis"
PROPIO = "CNM160812AB1"

SIN_FACTURA = {
    ("2026-07-27", "500.00", "MERCADO PAGO"),
    ("2026-06-16", "877.00", "MERCADO PAGO 1"),
    ("2026-08-16", "304.00", "FRANCISCO J. MORALES"),
    ("2026-08-27", "442.00", "SOFIA HERNANDEZ"),
}


def _cfdis():
    files = sorted(DIR.rglob("*.xml"))
    assert len(files) == 162, len(files)
    cfdis = [cx.parsear_archivo(p, "company_001", PROPIO, base=DIR) for p in files]
    assert len({c.uuid for c in cfdis}) == len(cfdis)
    assert all(c.subtotal + c.iva == c.total for c in cfdis)
    return cfdis


def _banco():
    rows = list(csv.DictReader(open(REPO / "seed" / "transactions.csv", encoding="utf-8")))
    dep = {r["deposito"] for r in rows if r["tipo"] == "ingreso"}
    ret = {r["retiro"] for r in rows if r["tipo"] == "egreso"}
    return rows, dep, ret


def test_conteos_y_tipos():
    cfdis = _cfdis()
    emi = [c for c in cfdis if c.tipo == "emitido"]
    rec = [c for c in cfdis if c.tipo == "recibido"]
    assert len(emi) == 16 and len(rec) == 146
    assert all(c.emisor_rfc == PROPIO for c in emi)
    assert all(c.receptor_rfc == PROPIO for c in rec)


def test_pareo_montos_banco():
    cfdis = _cfdis()
    _, dep, ret = _banco()
    for c in cfdis:
        if c.tipo == "recibido":
            assert f"{c.total:.2f}" in ret, c.xml_path
    pagados = [c for c in cfdis if c.tipo == "emitido" and f"{c.total:.2f}" in dep]
    impagados = [c for c in cfdis if c.tipo == "emitido" and f"{c.total:.2f}" not in dep]
    assert len(pagados) == 11 and len(impagados) == 5
    assert sum((c.total for c in impagados), Decimal("0")) == Decimal("76550.00")


def test_cuatro_sin_factura():
    cfdis = _cfdis()
    rows, _, _ = _banco()
    rec = [c for c in cfdis if c.tipo == "recibido"]
    # los 4 elegidos no tienen XML con su (total, rfc emisor)
    for fecha, retiro, comercio in SIN_FACTURA:
        fila = next(r for r in rows
                    if r["fecha"][:10] == fecha and r["retiro"] == retiro
                    and r["comercio"] == comercio)
        assert not any(c.emisor_rfc == fila["rfc"] and f"{c.total:.2f}" == retiro
                       for c in rec), (fecha, retiro, comercio)
    # todo otro egreso con RFC (salvo comisiones bancarias) sí tiene XML
    cubiertos = 0
    for r in rows:
        if r["tipo"] != "egreso" or not r["rfc"] or r["categoria"] in ("comision", "iva_comision"):
            continue
        key = (r["fecha"][:10], r["retiro"], r["comercio"])
        tiene = any(c.emisor_rfc == r["rfc"] and f"{c.total:.2f}" == r["retiro"] for c in rec)
        if key in SIN_FACTURA:
            assert not tiene, key
        else:
            assert tiene, key
            cubiertos += 1
    assert cubiertos == len(rec)
