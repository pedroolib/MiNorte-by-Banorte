"""Parser de estados de cuenta Banorte (Enlace Negocios / PFAE) en PDF.

Lee el texto con layout preservado (pdftotext -layout) y extrae el
DETALLE DE MOVIMIENTOS por posición de columnas:

    FECHA | DESCRIPCIÓN | MONTO DEL DEPOSITO | MONTO DEL RETIRO | SALDO

Los importes se clasifican por posición X del FIN del número, medida sobre
la línea COMPLETA (sin recortar fecha):
    <=136 → depósito, <=170 → retiro, resto → saldo.
Soporta devoluciones con signo al final ("699.88-") y filas donde la fecha
va pegada a la descripción ("01-MAR-23COMPRA ...").

Solo procesa cuentas Banorte Enlace (filtra secciones BBVA u otras cuentas
del mismo PDF). Cada movimiento queda etiquetado con su cuenta.

La validación es contable, no visual: la cadena de saldos debe cerrar
(saldo[i] == saldo[i-1] + deposito - retiro) y los totales del mes deben
coincidir con el RESUMEN del periodo. Si el layout cambia, la validación
grita en vez de devolver datos corruptos.

PII: este módulo nunca anonimiza; eso lo hace scripts/build_seed_from_pdf.py
antes de escribir seed/transactions.csv. Los PDFs viven en seed/private/.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from pathlib import Path

MESES = {
    "ENE": 1, "FEB": 2, "MAR": 3, "ABR": 4, "MAY": 5, "JUN": 6,
    "JUL": 7, "AGO": 8, "SEP": 9, "OCT": 10, "NOV": 11, "DIC": 12,
}

_ROW_START = re.compile(
    r"^\s*(\d{2})-(ENE|FEB|MAR|ABR|MAY|JUN|JUL|AGO|SEP|OCT|NOV|DIC)-(\d{2})\s*(.*\S)\s*$"
)
_AMOUNT = re.compile(r"\$?\s?\d{1,3}(?:,\d{3})*\.\d{2}(-?)")
_PAGE_NUM = re.compile(r"^\s*\d+\s*/\s*\d+\s*$")
# "ENLACE NEGOCIOS BASICA   0211807410 ..." en RESUMEN INTEGRAL.
# Anclado a inicio de línea para no confundir con "INVERSION ENLACE ...".
_PRODUCTO = re.compile(r"^\s*(ENLACE NEGOCIOS (?:PFAE|BASICA))\s+(\d{7,})")
# Cabecera de columnas: "FECHA DESCRIPCIÓN ... MONTO DEL DEPOSITO ... SALDO"
_CABECERA = re.compile(r"MONTO DEL DEPOSITO\s+MONTO DEL RETIRO\s+SALDO")

# Marcas que cierran la sección. Las de otro banco/cuenta van ancladas para
# no chocar con texto inline ("BBVA BANCOMER HORA LIQ" es Banorte válido).
_SECTION_END_SUBSTRING = (
    "Línea Directa", "Banco Mercantil del Norte", "Nuevo Leon",
    "Ganancia Anual Total", "COMPROBANTE FISCAL",
    "Referencia de Abreviaturas", "Advertencia:", "Aviso de privacidad",
    "Consultas, Reclamaciones", "Cargos Objetados", "Detalle de la tarjeta",
    "Resumen de comisiones", "Los productos anteriormente",
)
_SECTION_END_ANCLADO = re.compile(
    r"^\s*(OTROS|BBVA MEXICO|VERSATIL NEGOCIOS|No\. Cuenta|No\. Cliente)\b"
)
# Continuaciones con desglose informativo (nunca son importes del movimiento):
# "CVE RASTREO: ... RFC: ... IVA: 000000000039.32", "BBVA BANCOMER HORA LIQ: ..."
_DETALLE_INFORMATIVO = ("RASTREO", "HORA LIQ", "RFC", "IVA:", "CLABE", "BENEF")
_SECTION_START = "DETALLE DE MOVIMIENTOS"
_HEADER_NOISE = ("ESTADO DE CUENTA", "Enlace Negocios", "Inversión Enlace",
                 "Inversion Enlace", "FECHA DESCRIPCI")

# Geometría de columnas: la grilla X de pdftotext -layout es absoluta
# (los montos van alineados a la derecha en la misma X en todas las páginas;
# lo que varía es el texto de las cabeceras, por eso NO se calibra con ellas).
# Medido sobre ambos PDFs: depósitos terminan en 120-124, retiros en ~139-157,
# saldos en ~172-193, desgloses informativos (IVA) en <=95.
@dataclass
class Zonas:
    fin_deposito: float = 124.0
    fin_retiro: float = 153.0
    fin_saldo: float = 166.0
    ancho: float = 12.0


def _calibrar_zonas(cabecera: str) -> Zonas:
    """Se mantiene por compatibilidad; la grilla es fija (ver arriba)."""
    return Zonas()

TOLERANCIA = Decimal("0.02")


@dataclass
class Movimiento:
    fecha: date
    descripcion: str
    deposito: Decimal = Decimal("0")
    retiro: Decimal = Decimal("0")
    saldo: Decimal = Decimal("0")
    cuenta: str = ""
    es_saldo_anterior: bool = False
    # importes con decimales fuera de columnas (se resuelven por cadena)
    candidatos: list[Decimal] = field(default_factory=list, repr=False)
    crudo: str = field(default="", repr=False)


def _parse_monto(s: str, negativo: str) -> Decimal:
    v = Decimal(s.replace(",", ""))
    return -v if negativo == "-" else v


def extraer_texto(pdf: Path) -> str:
    """Extrae texto con layout. Requiere poppler (pdftotext)."""
    binario = shutil.which("pdftotext")
    if not binario:
        raise RuntimeError("pdftotext no encontrado (instala poppler-utils)")
    out = subprocess.run(
        [binario, "-layout", str(pdf), "-"],
        capture_output=True, text=True, check=True,
    )
    return out.stdout


def _es_ruido(linea: str) -> bool:
    s = linea.strip()
    if not s or _PAGE_NUM.match(linea):
        return True
    return any(h in linea for h in _HEADER_NOISE)


def parsear_texto(
    texto: str, cuentas: set[str] | None = None
) -> list[Movimiento]:
    """Parsea el DETALLE DE MOVIMIENTOS. Si `cuentas` se da, solo esas."""
    movs: list[Movimiento] = []
    dentro = False
    omitir_seccion = False  # subcuenta de inversión ("SIN MOVIMIENTOS")
    cuenta_actual = ""
    zonas = Zonas()
    actual: list[str] | None = None

    def _cerrar():
        nonlocal actual
        if actual:
            m = _materializar(actual, cuenta_actual, zonas)
            if (
                m
                and not omitir_seccion
                and (cuentas is None or m.cuenta in cuentas)
            ):
                movs.append(m)
            actual = None

    for linea in texto.splitlines():
        prod = _PRODUCTO.match(linea)
        if prod:
            cuenta_actual = prod.group(2)
        if _CABECERA.search(linea):
            zonas = _calibrar_zonas(linea)
        if _SECTION_START in linea:
            _cerrar()
            dentro = True
            omitir_seccion = False
            continue
        if dentro and (
            any(marca in linea for marca in _SECTION_END_SUBSTRING)
            or _SECTION_END_ANCLADO.match(linea)
        ):
            _cerrar()
            dentro = False
            continue
        if not dentro:
            continue
        if "INVERSI" in linea.upper() and "ENLACE" in linea.upper():
            # subsección de inversión: no aporta movimientos
            _cerrar()
            omitir_seccion = True
            continue
        if _es_ruido(linea):
            continue
        if "SIN MOVIMIENTOS" in linea:
            _cerrar()
            continue
        if _ROW_START.match(linea):
            _cerrar()
            actual = [linea]
        elif actual is not None and linea.strip():
            actual.append(linea)

    _cerrar()
    return movs


def _materializar(lineas: list[str], cuenta: str, zonas: Zonas) -> Movimiento | None:
    m0 = _ROW_START.match(lineas[0])
    assert m0
    dia, mes_txt, anio = m0.group(1), m0.group(2), m0.group(3)
    fecha = date(2000 + int(anio), MESES[mes_txt], int(dia))

    def _zona(x: float) -> str | None:
        z = zonas
        if z.fin_deposito - z.ancho <= x <= z.fin_deposito + 6:
            return "deposito"
        if z.fin_retiro - z.ancho <= x <= z.fin_retiro + 6:
            return "retiro"
        if x >= z.fin_saldo - 8:
            return "saldo"
        return None  # fuera de columnas (IVA en detalle, referencias)

    saldos: list[Decimal] = []
    candidatos: list[Decimal] = []  # importes fuera de columnas (ej. tiempo aire)
    deposito = retiro = Decimal("0")
    textos: list[str] = []
    for i, ln in enumerate(lineas):
        # coordenadas siempre sobre la línea completa
        es_informativa = i > 0 and any(k in ln for k in _DETALLE_INFORMATIVO)
        if not es_informativa:
            for am in _AMOUNT.finditer(ln):
                crudo_monto = am.group()
                es_negativo = crudo_monto.endswith("-")
                valor = _parse_monto(crudo_monto.lstrip("$ ").rstrip("-"),
                                     "-" if es_negativo else "")
                x_fin = am.end() - (1 if es_negativo else 0)
                z = _zona(x_fin)
                if z == "saldo":
                    saldos.append(valor)
                elif z == "deposito":
                    deposito += valor
                elif z == "retiro":
                    retiro += valor
                else:
                    candidatos.append(valor)
                # fuera de columnas (IVA en detalle, referencias): candidatos
        # descripción con texto fiel (SIN quitar importes: quitarlos a medias
        # dejaba artefactos como "IVA: 000000004"). Los montos ya quedaron
        # clasificados por posición; aquí solo se normaliza whitespace.
        cuerpo = m0.group(4) if i == 0 else ln
        if cuerpo.strip():
            textos.append(" ".join(cuerpo.split()))

    if not saldos and deposito == 0 and retiro == 0 and not candidatos:
        return None
    saldo = saldos[-1] if saldos else Decimal("0")
    descripcion = re.sub(r"\s+", " ", " ".join(textos)).strip()
    es_saldo = descripcion.upper().startswith("SALDO ANTERIOR")
    return Movimiento(
        fecha=fecha, descripcion=descripcion, deposito=deposito,
        retiro=retiro, saldo=saldo, cuenta=cuenta,
        es_saldo_anterior=es_saldo, candidatos=candidatos,
        crudo="\n".join(lineas),
    )


def resolver_ambiguos(movs: list[Movimiento]) -> int:
    """Resuelve filas con importe fuera de columnas (ej. tiempo aire en BXI).

    Usa la cadena de saldos: el candidato va al lado que hace cerrar
    saldo == previo + deposito - retiro. Devuelve cuántos resolvió.
    """
    resueltos = 0
    previo: Decimal | None = None
    for m in movs:
        if m.es_saldo_anterior:
            previo = m.saldo
            continue
        if previo is None:
            previo = m.saldo - m.deposito + m.retiro
            continue
        if (
            m.deposito == 0 and m.retiro == 0
            and len(m.candidatos) == 1 and m.saldo != 0
        ):
            c = m.candidatos[0]
            if abs(previo - c - m.saldo) <= TOLERANCIA:
                m.retiro = c
                resueltos += 1
            elif abs(previo + c - m.saldo) <= TOLERANCIA:
                m.deposito = c
                resueltos += 1
        previo = m.saldo
    return resueltos


def validar_cadena(movs: list[Movimiento]) -> list[str]:
    """Verifica la cadena de saldos. Devuelve errores (vacía = ok).

    Cada SALDO ANTERIOR reinicia la cadena (nuevo periodo).
    """
    errores: list[str] = []
    previo: Decimal | None = None
    for i, m in enumerate(movs):
        if m.es_saldo_anterior:
            previo = m.saldo
            continue
        if previo is None:
            previo = m.saldo - m.deposito + m.retiro
            continue
        esperado = previo + m.deposito - m.retiro
        if abs(esperado - m.saldo) > TOLERANCIA:
            errores.append(
                f"fila {i} {m.fecha} {m.descripcion[:50]!r}: "
                f"esperado {esperado} vs saldo {m.saldo}"
            )
        previo = m.saldo
    return errores


def totales(movs: list[Movimiento]) -> tuple[Decimal, Decimal]:
    """(total_depósitos, total_retiros) excluyendo SALDO ANTERIOR."""
    dep = sum((m.deposito for m in movs if not m.es_saldo_anterior), Decimal("0"))
    ret = sum((m.retiro for m in movs if not m.es_saldo_anterior), Decimal("0"))
    return dep, ret


def partir_periodos(movs: list[Movimiento]) -> list[list[Movimiento]]:
    """Parte por cada SALDO ANTERIOR (periodo)."""
    periodos: list[list[Movimiento]] = []
    actual: list[Movimiento] = []
    for m in movs:
        if m.es_saldo_anterior and actual:
            periodos.append(actual)
            actual = []
        actual.append(m)
    if actual:
        periodos.append(actual)
    return periodos
