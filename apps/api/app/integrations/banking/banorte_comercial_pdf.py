"""Parser de estados de cuenta Banorte (Cuenta Comercio Empresarial) en PDF.

Formato distinto a Banorte: dos fechas (OPER/LIQ), columnas
CARGOS | ABONOS | SALDO OPERACIÓN | SALDO LIQUIDACIÓN, descripciones
libres SIN RFC, comercios/personas en líneas de detalle, sin fila de
SALDO ANTERIOR (el previo viene del resumen del periodo).

Clasificación por posición X del FIN del importe (línea completa):
grilla absoluta de pdftotext -layout, igual técnica que banorte_pdf.
Validación contable: cadena de saldos + totales vs resumen.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from pathlib import Path

from app.integrations.banking.banorte_pdf import extraer_texto

MESES = {
    "ENE": 1, "FEB": 2, "MAR": 3, "ABR": 4, "MAY": 5, "JUN": 6,
    "JUL": 7, "AGO": 8, "SEP": 9, "OCT": 10, "NOV": 11, "DIC": 12,
}

_ROW = re.compile(
    r"^\s*(\d{2})/([A-Z]{3})\s+(\d{2})/([A-Z]{3})\s+(.*\S)\s*$"
)
_AMOUNT = re.compile(r"\$?\s?\d{1,3}(?:,\d{3})*\.\d{2}(-?)")
_PAGE_NUM = re.compile(r"^\s*PAGINA\s+\d+\s*/\s*\d+", re.IGNORECASE)

_SECTION_START = "Detalle de Movimientos"
# OJO: este formato no repite el título en continuaciones (a diferencia
# del formato Enlace): una vez dentro, solo salimos en el cierre real.
# Los footers se ignoran. Los literales "BBVA..." de abajo matchean el
# texto impreso del PDF real y no se tocan.
# como ruido (no traen fechas de movimiento).
_SECTION_END = (
    "Total de Movimientos",
)
_FOOTER_NOISE = (
    "BBVA MEXICO", "Av. Paseo de la Reforma", "Línea BBVA", "www.bbva.mx",
    "Con BBVA", "GAT ", "CAT ", "Estimado Cliente",
)
_HEADER_NOISE = ("Estado de Cuenta", "CUENTA COMERCIO", "No. de Cuenta",
                 "No. de Cliente", "FECHA", "OPER   LIQ", "DESCRIPCI")

# Fronteras de columna (fin del importe; medido en el PDF real)
X_RETIRO_MAX = 108
X_DEPOSITO_MAX = 120

TOLERANCIA = Decimal("0.02")


@dataclass
class MovimientoBanorte:
    fecha_oper: date
    fecha_liq: date
    descripcion: str
    comercio: str
    deposito: Decimal = Decimal("0")
    retiro: Decimal = Decimal("0")
    saldo: Decimal = Decimal("0")
    tiene_saldo: bool = False
    crudo: str = field(default="", repr=False)


def _monto(s: str, neg: str) -> Decimal:
    v = Decimal(s.replace(",", "").lstrip("$ "))
    return -v if neg == "-" else v


def _es_ruido(linea: str) -> bool:
    s = linea.strip()
    if not s or _PAGE_NUM.match(linea):
        return True
    if any(m in linea for m in _FOOTER_NOISE):
        return True
    return any(h in linea for h in _HEADER_NOISE)


def parsear_texto(texto: str, anio: int) -> list[MovimientoBanorte]:
    movs: list[MovimientoBanorte] = []
    dentro = False
    actual: list[str] | None = None

    def _cerrar():
        nonlocal actual
        if actual:
            m = _materializar(actual, anio)
            if m:
                movs.append(m)
            actual = None

    for linea in texto.splitlines():
        if _SECTION_START in linea:
            _cerrar()
            dentro = True
            continue
        if dentro and any(m in linea for m in _SECTION_END):
            _cerrar()
            dentro = False
            continue
        if not dentro or _es_ruido(linea):
            continue
        if _ROW.match(linea):
            _cerrar()
            actual = [linea]
        elif actual is not None and linea.strip():
            actual.append(linea)
    _cerrar()
    return movs


def _materializar(lineas: list[str], anio: int) -> MovimientoBanorte | None:
    m0 = _ROW.match(lineas[0])
    assert m0
    d1, m1, d2, m2, resto = m0.groups()
    fecha_oper = date(anio, MESES[m1], int(d1))
    fecha_liq = date(anio, MESES[m2], int(d2))

    deposito = retiro = Decimal("0")
    saldos: list[Decimal] = []
    textos: list[str] = [resto]
    for i, ln in enumerate(lineas):
        cuerpo = resto if i == 0 else ln
        for am in _AMOUNT.finditer(ln if i else ln):
            val = _monto(am.group().rstrip("-"), "-" if am.group().endswith("-") else "")
            x = am.end() - (1 if am.group().endswith("-") else 0)
            if x <= X_RETIRO_MAX:
                retiro += val
            elif x <= X_DEPOSITO_MAX:
                deposito += val
            else:
                saldos.append(val)
        if i:
            textos.append(" ".join(ln.split()))
    descripcion = re.sub(r"\s+", " ", " ".join(textos)).strip()
    comercio = _extraer_comercio(lineas, resto)
    saldo = saldos[0] if saldos else Decimal("0")
    if not deposito and not retiro and not saldos:
        return None
    return MovimientoBanorte(fecha_oper, fecha_liq, descripcion, comercio,
                          deposito, retiro, saldo, bool(saldos),
                          "\n".join(lineas))


def _limpiar_detalle(texto: str) -> str:
    """Deja solo palabras con letras: quita refs, CLABEs y códigos."""
    STOP = {"BNET", "MAC", "DEL", "REF", "CIA", "GUIA"}
    partes = []
    for tok in texto.split():
        t = re.sub(r"^[\d\-/]+", "", tok)
        if len(t) < 3 or t.isdigit():
            continue
        if re.search(r"\d", t) and len(t) >= 6:
            continue
        if t.upper() in STOP:
            continue
        if not partes or partes[-1].upper() != t.upper():
            partes.append(t)
    return " ".join(partes)


def _extraer_comercio(lineas: list[str], resto: str) -> str:
    """Beneficiario real: en Banorte vive en el detalle, no en el encabezado."""
    up = resto.upper()
    detalle = [ln for ln in lineas[1:]
               if ln.strip() and not ln.upper().strip().startswith("DEL ")]
    # SPEI (enviado o recibido): ÚLTIMA porción útil (el beneficiario va
    # al final; las primeras líneas son sucursales/claves como "MXL 45556")
    if up.startswith("SPEI RECIBIDO") or up.startswith("SPEI ENVIADO"):
        candidatos = []
        for ln in detalle:
            p = _limpiar_detalle(ln)
            if len(p) >= 4 and not p.upper().startswith("SPEI"):
                candidatos.append(p)
        if candidatos:
            return candidatos[-1].title()[:60]
        banco = re.sub(r"^SPEI\s+(RECIBIDO|ENVIADO)\s*", "", resto, flags=re.I).strip()
        return (f"SPEI {banco}".title()[:60]) if banco else ""
    # PAGO CUENTA DE TERCERO: concepto tras "BNET <clave>"
    if up.startswith("PAGO CUENTA DE TERCERO"):
        for ln in detalle:
            m2 = re.search(r"BNET\s+\d+\s+(.+)", ln.upper())
            if m2:
                nombre = _limpiar_detalle(m2.group(1))
                if len(nombre) >= 4:
                    return nombre.title()[:60]
        return ""
    # primera línea con nombre propio (GONHERMEX,SA DE CV)
    m3 = re.match(r"^([A-ZÑ][A-ZÑ,\.\s]{3,}?)(?:\s+\d|\s+[A-Z]{2,}\d|$)", resto)
    if m3 and not up.startswith(("SPEI", "VENTAS", "PAGO", "CHEQUE",
                                 "EMISION", "COM ", "IVA ", "APLI ",
                                 "COMISION", "RECIBO", "SERV ")):
        return m3.group(1).strip().title()[:60]
    # ventas TPV anónimas
    if up.startswith("VENTAS"):
        return "VENTAS TPV"
    if up.startswith("CHEQUE PAGADO"):
        nombre = _limpiar_detalle(" ".join(detalle))
        return nombre.title()[:60] if len(nombre) >= 4 else ""
    return ""


def clasificar_banorte(descripcion: str) -> tuple[str, bool]:
    """(categoria, es_interno) para movimientos Banorte. Orden importa."""
    d = descripcion.upper()
    if "TRASPADO ENTRE CUENTAS" in d or "TRASPASO ENTRE CUENTAS" in d:
        return "traspaso_interno", True
    if "PAGO TARJETA DE CREDITO" in d or "PAGO INTERBANCARIO" in d:
        return "pago_tdc", True
    if d.startswith("VENTAS"):
        return "ventas_tpv", False
    if ("COM VTAS" in d or "TASA DE DES" in d or "IVA TASA" in d
            or "IVA COM" in d or "EMISION LIBRAMIE" in d
            or "SERV BANCA" in d):
        return "comision", False
    if d.startswith("SPEI RECIBIDO"):
        return "spei_recibido", False
    if "DEPOSITO DE TERCERO" in d:
        # abono en ventanilla sin contraparte identificada (BMRCASH)
        return "deposito_tercero", False
    if d.startswith("SPEI ENVIADO"):
        return "spei_enviado", False
    if "GUIA:" in d and "REF:" in d and "CIE:" in d:
        # orden de pago interbancaria a proveedor (CIE)
        return "spei_enviado", False
    if d.startswith("PAGO CUENTA DE TERCERO"):
        return "traspaso_terceros", False
    if d.startswith("CHEQUE PAGADO"):
        return "cheque", False
    if re.search(r"NOMINA|SUELDO|SALARIO|AGUINALDO", d):
        return "nomina", False
    if re.search(r"GOBIERNO|SAT[^A-Z]|ISR|TESORERIA|REFERENCIADO|IMPUESTO", d):
        return "impuestos", False
    if d.startswith("RECIBO NO"):
        return "otro", False
    return "otro", False


def validar_cadena(movs: list[MovimientoBanorte],
                   saldo_inicial: Decimal) -> list[str]:
    errores: list[str] = []
    previo = saldo_inicial
    for i, m in enumerate(movs):
        esperado = previo + m.deposito - m.retiro
        if m.tiene_saldo and abs(esperado - m.saldo) > TOLERANCIA:
            errores.append(f"fila {i} {m.fecha_oper} {m.descripcion[:45]!r}: "
                           f"esperado {esperado} vs impreso {m.saldo}")
        previo = esperado
    return errores, previo


def totales(movs: list[MovimientoBanorte]) -> tuple[Decimal, Decimal]:
    dep = sum((m.deposito for m in movs), Decimal("0"))
    ret = sum((m.retiro for m in movs), Decimal("0"))
    return dep, ret
