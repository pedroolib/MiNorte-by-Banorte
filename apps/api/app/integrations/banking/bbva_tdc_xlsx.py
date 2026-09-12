"""Parser del estado de cuenta TDC BBVA en XLSX (piloto, datos reales).

Formato observado (una hoja, sin encabezado formal):
  fila par:   ("31 jul.", DESCRIPCION, IMPORTE, None)
  fila impar: (2026, TIPO, None, None)   <- TIPO aplica a la fila anterior

TIPO ∈ {"Compra", "Ingresos en efectivo", "Pago de tarjeta de crédito"}.
Signo: cargos positivos, abonos (INTERN.PAGO TDC) negativos.
Sin columna de saldo: los renglones resultantes llevan saldo vacío.

Reglas de mapeo (espejo de clasificar_bbva en chequera):
  Compra, importe > 0            -> egreso, categoria "otro"
  Compra ADMINISTRACION TARJ.    -> egreso, categoria "comision"
  Ingresos en efectivo (abono)   -> ingreso, es_interno=1, categoria "pago_tdc"
  Pago de tarjeta (anualidad)    -> egreso, categoria "comision"
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path

MESES_ES = {"ene": 1, "feb": 2, "mar": 3, "abr": 4, "may": 5, "jun": 6,
            "jul": 7, "ago": 8, "sep": 9, "oct": 10, "nov": 11, "dic": 12}

TIPOS_VALIDOS = {"Compra", "Ingresos en efectivo", "Pago de tarjeta de crédito"}


@dataclass
class MovimientoTDC:
    fecha: date
    descripcion: str
    tipo_mov: str
    importe: Decimal


def _parse_fecha(raw: str, year: int) -> date:
    partes = raw.strip().lower().replace(".", "").split()
    if len(partes) != 2 or partes[1] not in MESES_ES:
        raise ValueError(f"fecha inesperada: {raw!r}")
    return date(year, MESES_ES[partes[1]], int(partes[0]))


def _parse_importe(raw) -> Decimal:
    try:
        return Decimal(str(raw))
    except (InvalidOperation, ValueError, TypeError):
        raise ValueError(f"importe inesperado: {raw!r}")


def parsear_xlsx(path: str | Path, year: int = 2026) -> list[MovimientoTDC]:
    """Lee el XLSX y devuelve movimientos (fecha, descripcion, tipo, importe)."""
    import openpyxl

    ws = openpyxl.load_workbook(path, data_only=True).active
    filas = list(ws.iter_rows(values_only=True))
    movs: list[MovimientoTDC] = []
    i = 0
    empezo = False
    while i < len(filas):
        a, b, c, *_ = (list(filas[i]) + [None] * 4)[:4]
        if a is None and (b is None or str(b).strip() in ("",)):
            i += 1
            continue
        if isinstance(a, int):  # fila de TIPO suelta sin par: se ignora
            i += 1
            continue
        try:
            _parse_fecha(str(a), year)
            es_fecha = True
        except (ValueError, AttributeError):
            es_fecha = False
        if not es_fecha:
            if empezo:
                raise ValueError(f"fila {i + 1} inesperada tras datos: {(a, b)!r}")
            i += 1  # título/encabezado previo a los datos: se salta
            continue
        empezo = True
        if i + 1 >= len(filas):
            raise ValueError(f"fila {i + 1} sin fila de tipo posterior")
        a2, b2, *_ = (list(filas[i + 1]) + [None] * 4)[:4]
        if not (isinstance(a2, int) and a2 == year and str(b2).strip() in TIPOS_VALIDOS):
            raise ValueError(f"fila {i + 2} no es tipo válido: {(a2, b2)!r}")
        if not isinstance(a, str) or c is None:
            raise ValueError(f"fila {i + 1} incompleta: {(a, b, c)!r}")
        movs.append(MovimientoTDC(
            fecha=_parse_fecha(a, year),
            descripcion=str(b).strip(),
            tipo_mov=str(b2).strip(),
            importe=_parse_importe(c),
        ))
        i += 2
    if not movs:
        raise ValueError("sin movimientos en el XLSX")
    return movs


def a_csv_row(m: MovimientoTDC, seq: int, company_id: str,
              account_id: str) -> dict:
    """Mapea a fila del CSV espejo (mismas columnas que build_pilot_bbva)."""
    d = m.descripcion.upper()
    if m.tipo_mov == "Ingresos en efectivo":
        tipo, dep, ret, interno, cat = "ingreso", abs(m.importe), Decimal("0"), "1", "pago_tdc"
    else:
        tipo, dep, ret, interno = "egreso", Decimal("0"), abs(m.importe), "0"
        if "ADMINISTRACION TARJ" in d:
            cat = "comision"
        else:
            cat = "otro"
    return {
        "id": f"txn_pilot_tdc{seq:04d}",
        "company_id": company_id,
        "account_id": account_id,
        "fecha": f"{m.fecha.isoformat()}T12:00:00-06:00",
        "descripcion": m.descripcion,
        "comercio": m.descripcion,
        "rfc": "",
        "tipo": tipo,
        "deposito": str(dep),
        "retiro": str(ret),
        "saldo": "",
        "es_interno": interno,
        "categoria": cat,
        "source": "bbva_mock",
    }


def validar(movs: list[MovimientoTDC], year: int, mes: int) -> dict:
    """Chequeos estructurales. Devuelve resumen para reportar."""
    assert all(m.fecha.year == year and m.fecha.month == mes for m in movs), \
        "hay fechas fuera del periodo esperado"
    compras = sum((m.importe for m in movs if m.tipo_mov == "Compra"), Decimal("0"))
    abonos = sum((-m.importe for m in movs if m.tipo_mov == "Ingresos en efectivo"), Decimal("0"))
    anualidad = sum((m.importe for m in movs if m.tipo_mov == "Pago de tarjeta de crédito"), Decimal("0"))
    assert all(m.importe > 0 for m in movs if m.tipo_mov != "Ingresos en efectivo"), \
        "cargo no positivo en Compra/anualidad"
    assert all(m.importe < 0 for m in movs if m.tipo_mov == "Ingresos en efectivo"), \
        "abono no negativo en Ingresos en efectivo"
    return {"n": len(movs), "compras": compras, "abonos": abonos, "anualidad": anualidad}
