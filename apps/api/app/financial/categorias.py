"""Taxonomía de rubros PyME + clasificación híbrida (T6).

Fuentes por prioridad (back-fill):
1. CFDI conciliado: ClaveProdServ (SAT estándar) -> rubro. La factura manda.
2. Directorio de comercios (tarjeta/domiciliados conocidos).
3. Keywords de la descripción bancaria (SPEI, nómina, impuestos...).
4. Categoría de flujo (impuestos/comisiones van directo).
5. Fallback honesto: "varios" (genérico real) o "por_clasificar" (sin pista).

La app de personas clasifica por MCC de la red de tarjetas; en empresas
el estado no trae columna de categoría y el SPEI no tiene MCC, por eso
el híbrido + el CFDI como árbitro.
"""

from __future__ import annotations

import re

RUBROS = [
    "nomina",
    "proveedores_materiales",
    "honorarios",
    "servicios_generales",
    "combustible",
    "consumibles",
    "transporte_paqueteria",
    "arrendamiento",
    "telecom",
    "seguros",
    "impuestos",
    "comisiones_bancarias",
    "equipo_computo",
    "traspaso_interno",
    "varios",
    "por_clasificar",
]

# ClaveProdServ (8 dígitos) -> rubro. Cubre el 100% del seed.
SAT_MAP = {
    "72101500": "servicios_generales",   # servicios de mantenimiento/reparación
    "72101501": "servicios_generales",
    "31161500": "proveedores_materiales",  # refacciones y repuestos
    "78101800": "proveedores_materiales",  # fletes (insumo logístico)
    "78102200": "transporte_paqueteria",   # mensajería y paquetería
    "78111800": "arrendamiento",           # arrendamiento de transporte
    "15101500": "combustible",
    "50161500": "consumibles",             # materiales de consumo
    "43211500": "equipo_computo",
    "83111500": "telecom",
    "84131500": "seguros",
    "80101500": "servicios_generales",     # consultoría/servicios profesionales
    "80111600": "servicios_generales",
}

# Substring de comercio (mayúsculas) -> rubro. Comercios del seed + cadenas.
MERCHANT_MAP = [
    ("GASOL", "combustible"),
    ("SUPER LA CANASTA", "consumibles"),
    ("SUPER EXPRESS", "consumibles"),
    ("COSTCO", "consumibles"),
    ("OXXO", "consumibles"),
    ("MERCADO PAGO", "consumibles"),
    ("MERPAGO", "consumibles"),
    ("APPLE", "equipo_computo"),
    ("ELECTRONICA INDUSTRIAL", "proveedores_materiales"),
    ("DHL", "transporte_paqueteria"),
    ("PAQUETERIA EXPRESS", "transporte_paqueteria"),
    ("TELMEX", "telecom"),
    ("TELCEL", "telecom"),
    ("RADIOMOVIL", "telecom"),
    ("PAGO SERV CEL", "telecom"),
    ("ARRENDADORA", "arrendamiento"),
    ("VOLKSWAGEN", "arrendamiento"),
    ("VW LEASING", "arrendamiento"),
    ("SEGUROS DEL NORTE", "seguros"),
    ("POTENCIA HIDRAULICA", "proveedores_materiales"),
    ("PAYPAL", "servicios_generales"),
    ("BANORTE", "comisiones_bancarias"),
]

# (regex descripción, rubro) en orden. SPEI y cargos no-tarjeteros.
KEYWORD_RULES = [
    (r"NOMINA", "nomina"),
    (r"LDC-IMSS|IMSS", "impuestos"),
    (r"PAGO REFERENCIADO.*IMPUESTO|IMPUESTO.*REFERENCIADO", "impuestos"),
    (r"COMISION|MEMBRESIA|I\.V\.A\. ORDEN|IVA MEMBRESIA", "comisiones_bancarias"),
    (r"TRASPASO INTERNO", "traspaso_interno"),
    (r"DEV\.SPEI|MOT DEV", "varios"),
    (r"TIEMPO AIRE", "telecom"),
    (r"PAGO A PROVEEDOR|PAGO PO \d+", "proveedores_materiales"),
    (r"COBRO AUTOMATICO|PREST\.", "varios"),
    (r"CHEQUE PAGADO", "varios"),
    (r"DISPERSION|DISPERSI", "nomina"),
]


def rubro_por_clave(clave: str | None) -> str | None:
    """Mapeo SAT. None si la clave no está catalogada (revisar mapa)."""
    if not clave:
        return None
    return SAT_MAP.get(clave.strip())


def clasificar_rubro(descripcion: str, merchant: str = "",
                     categoria: str = "", cfdi_clave: str | None = None,
                     tipo: str = "egreso") -> str:
    """Rubro con prioridad: CFDI > merchant > keyword > categoría > fallback."""
    if tipo == "ingreso":
        return "traspaso_interno" if "TRASPASO INTERNO" in descripcion.upper() else "varios"
    if cfdi_clave:
        r = rubro_por_clave(cfdi_clave)
        if r:
            return r
    merch = (merchant or "").upper()
    texto = f"{merch} {descripcion.upper()}"
    for sub, rubro in MERCHANT_MAP:
        if sub in texto:
            return rubro
    for pat, rubro in KEYWORD_RULES:
        if re.search(pat, descripcion.upper()):
            return rubro
    if categoria == "impuestos":
        return "impuestos"
    if categoria in ("comision", "iva_comision"):
        return "comisiones_bancarias"
    if categoria == "traspaso_terceros":
        return "honorarios"
    if categoria in ("domiciliacion", "servicios"):
        return "servicios_generales"
    if categoria == "imss":
        return "impuestos"
    return "por_clasificar"


def cobertura(movimientos: list[tuple[str, str, str, str | None, str]]) -> dict:
    """{(desc, merchant, categoria, clave, tipo): rubro} + % clasificados."""
    out = {(d, m, c, k, t): clasificar_rubro(d, m, c, k, t)
           for d, m, c, k, t in movimientos}
    n = len(out)
    ok = sum(1 for r in out.values() if r not in ("por_clasificar",))
    return {"rubros": out, "cobertura": (ok / n) if n else 1.0, "total": n}
