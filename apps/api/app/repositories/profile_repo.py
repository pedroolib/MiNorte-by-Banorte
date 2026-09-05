"""Perfil del negocio + detección para prefill (T8).

business_profiles describe giro/ubicación/tamaño para contextualizar al
Consultor. La detección propone desde datos (rubros, CPs, volumen,
RFCs de clientes); el dueño confirma o corrige en /ajustes.
"""

from collections import Counter
from decimal import Decimal
from typing import Any

CERO = Decimal("0")

GIRO_POR_RUBRO = {
    "proveedores_materiales": "Servicios industriales / mantenimiento",
    "servicios_generales": "Servicios a negocios",
    "combustible": "Transporte y logística",
    "consumibles": "Comercio minorista",
    "transporte_paqueteria": "Transporte y logística",
    "arrendamiento": "Arrendamiento y servicios",
    "telecom": "Servicios de telecomunicaciones",
    "equipo_computo": "Tecnología y equipo",
    "nomina": "Servicios intensivos en personal",
}

# Prefijo CP -> (ciudad, estado). Solo lo verificable; resto -> "".
CP_CIUDAD = {
    "76": ("Querétaro", "Querétaro"),
    "66": ("Monterrey", "Nuevo León"),
    "64": ("Monterrey", "Nuevo León"),
    "03": ("Ciudad de México", "CDMX"),
    "80": ("Culiacán", "Sinaloa"),
}


def get_profile(sb: Any, company_id: str) -> dict | None:
    res = (sb.table("business_profiles").select("*")
           .eq("company_id", company_id).execute())
    return (res.data or [None])[0]


def upsert_profile(sb: Any, company_id: str, perfil: dict) -> dict:
    giro = (perfil.get("giro") or "").strip()
    ciudad = (perfil.get("ciudad") or "").strip()
    if not giro or not ciudad:
        raise ValueError("giro y ciudad son obligatorios")
    modelo = (perfil.get("modelo") or "mixto").strip().lower()
    if modelo not in ("b2b", "b2c", "mixto"):
        raise ValueError("modelo debe ser b2b, b2c o mixto")
    row = {"company_id": company_id, "giro": giro, "ciudad": ciudad,
           "estado": (perfil.get("estado") or "").strip(),
           "cp": (perfil.get("cp") or "").strip(),
           "tamanio": (perfil.get("tamanio") or "").strip(),
           "empleados": perfil.get("empleados"),
           "modelo": modelo,
           "notas": (perfil.get("notas") or "").strip()}
    (sb.table("business_profiles")
     .upsert(row, on_conflict="company_id").execute())
    return get_profile(sb, company_id) or row


def sugerir_perfil(txns, cfdis) -> dict:
    """Propuesta determinista desde datos. El dueño confirma en /ajustes."""
    # giro: rubro dominante de egresos no internos
    por_rubro: dict[str, Decimal] = {}
    for t in txns:
        if t.type == "egreso" and not t.es_interno:
            por_rubro[t.rubro] = por_rubro.get(t.rubro, CERO) + t.amount
    top = max(por_rubro, key=lambda k: por_rubro[k]) if por_rubro else ""
    # ubicación: moda de LugarExpedicion
    cps = Counter(c.lugar_expedicion for c in cfdis if c.lugar_expedicion)
    cp, ciudad, estado = "", "", ""
    if cps:
        cp = cps.most_common(1)[0][0]
        ciudad, estado = CP_CIUDAD.get(cp[:2], ("", ""))
    # tamaño por volumen anualizado (depósitos/mes * 12)
    meses = {(t.date.year, t.date.month) for t in txns}
    dep = sum((t.amount for t in txns if t.type == "ingreso"), CERO)
    anual = (dep / len(meses) * 12) if meses else CERO
    tamanio = ("micro" if anual <= 4_000_000 else
               "pequeña" if anual <= 100_000_000 else "mediana")
    # modelo por RFCs de clientes cobrados
    morales = fisicas = 0
    vistos = set()
    for t in txns:
        if t.type == "ingreso" and not t.es_interno and t.merchant_rfc:
            key = t.merchant_rfc.upper()
            if key not in vistos:
                vistos.add(key)
                if len(key) == 12:
                    morales += 1
                else:
                    fisicas += 1
    tot = morales + fisicas
    modelo = ("b2b" if tot and morales / tot > 0.7 else
              "b2c" if tot and fisicas / tot > 0.7 else "mixto")
    return {"giro": GIRO_POR_RUBRO.get(top, "Comercio y servicios"),
            "giro_origen": f"rubro dominante: {top or 's/d'}",
            "ciudad": ciudad, "estado": estado, "cp": cp,
            "tamanio": tamanio,
            "tamanio_origen": f"~${anual:,.0f}/año en depósitos",
            "modelo": modelo, "empleados": None, "notas": ""}
