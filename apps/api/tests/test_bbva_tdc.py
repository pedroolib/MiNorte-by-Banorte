"""Parser XLSX TDC: estructura, mapeo y validaciones (workbook sintético)."""

from decimal import Decimal

import pytest

from app.integrations.banking import bbva_tdc_xlsx as tdc


def _wb(path, filas):
    import openpyxl
    wb = openpyxl.Workbook()
    ws = wb.active
    for r in filas:
        ws.append(r)
    wb.save(path)


@pytest.fixture
def xlsx(tmp_path):
    p = tmp_path / "tdc.xlsx"
    _wb(p, [
        ("Movimientos TDC", None, None, None),
        ("Fecha de operación", "TIPO", None, None),
        ("10 jul.", "AUTOZONE 1", 500, None),
        (2026, "Compra", None, None),
        ("09 jul.", "123INTERN.PAGO TDC", -200, None),
        (2026, "Ingresos en efectivo", None, None),
        ("08 jul.", "ADMINISTRACION TARJ. TITULAR", 100, None),
        (2026, "Pago de tarjeta de crédito", None, None),
    ])
    return p


def test_parseo_y_mapeo(xlsx):
    movs = tdc.parsear_xlsx(xlsx, 2026)
    assert len(movs) == 3
    rows = [tdc.a_csv_row(m, i + 1, "c", "acc_tdc_001") for i, m in enumerate(movs)]
    assert rows[0]["tipo"] == "egreso" and rows[0]["retiro"] == "500"
    assert rows[0]["categoria"] == "otro" and rows[0]["es_interno"] == "0"
    assert rows[0]["id"] == "txn_pilot_tdc0001"
    assert rows[1]["tipo"] == "ingreso" and rows[1]["deposito"] == "200"
    assert rows[1]["es_interno"] == "1" and rows[1]["categoria"] == "pago_tdc"
    assert rows[2]["categoria"] == "comision"
    rep = tdc.validar(movs, 2026, 7)
    assert rep == {"n": 3, "compras": Decimal("500"),
                   "abonos": Decimal("200"), "anualidad": Decimal("100"),
                   "fuera_periodo": []}


def test_falla_fuerte_ante_layout_distinto(tmp_path):
    p = tmp_path / "mal.xlsx"
    _wb(p, [("10 jul.", "ALGO", 5, None), (2026, "Tipo raro", None, None)])
    with pytest.raises(ValueError, match="tipo válido"):
        tdc.parsear_xlsx(p, 2026)
    p2 = tmp_path / "vacio.xlsx"
    _wb(p2, [("nada", None, None, None)])
    with pytest.raises(ValueError):
        tdc.parsear_xlsx(p2, 2026)
