"""Parser REAL de CFDI 4.0 (XML del SAT).

La frontera mock es *cómo llegó el XML* (seed / sync simulado).
Todo lo posterior —extracción de UUID, emisor, impuestos, conceptos—
es parseo real con namespaces cfdi: y tfd:.

No valida sellos ni cadena original (fuera de alcance hackathon).
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from pathlib import Path
from xml.etree import ElementTree as ET

from app.schemas.cfdi import Cfdi

NS = {
    "cfdi": "http://www.sat.gob.mx/cfd/4",
    "tfd": "http://www.sat.gob.mx/TimbreFiscalDigital",
}


class CfdiError(ValueError):
    pass


def _dec(v: str | None, default: str = "0") -> Decimal:
    return Decimal(v if v not in (None, "") else default)


def parsear_xml(
    xml: str | Path,
    company_id: str,
    rfc_propio: str,
    xml_path: str | None = None,
) -> Cfdi:
    """Parsea un CFDI 4.0 a contrato Cfdi.

    tipo = 'emitido' si el emisor es la empresa, 'recibido' si no.
    """
    texto = Path(xml).read_text(encoding="utf-8") if isinstance(xml, Path) else xml
    try:
        root = ET.fromstring(texto)
    except ET.ParseError as e:
        raise CfdiError(f"XML inválido: {e}") from e

    if not root.tag.endswith("}Comprobante"):
        raise CfdiError(f"raíz inesperada: {root.tag}")

    emisor = root.find("cfdi:Emisor", NS)
    receptor = root.find("cfdi:Receptor", NS)
    if emisor is None or receptor is None:
        raise CfdiError("falta Emisor o Receptor")

    timbre = root.find("cfdi:Complemento/tfd:TimbreFiscalDigital", NS)
    if timbre is None or not timbre.get("UUID"):
        raise CfdiError("falta TimbreFiscalDigital con UUID")
    uuid = timbre.get("UUID", "").upper()

    # IVA = suma de traslados impuesto 002 (puede no haber)
    iva = Decimal("0")
    for tr in root.findall("cfdi:Impuestos/cfdi:Traslados/cfdi:Traslado", NS):
        if (tr.get("Impuesto") or "002") == "002":
            iva += _dec(tr.get("Importe"))

    conceptos = root.findall("cfdi:Conceptos/cfdi:Concepto", NS)
    concepto = "; ".join(
        (c.get("Descripcion") or "").strip() for c in conceptos if c.get("Descripcion")
    ) or "SIN DESCRIPCION"
    primero = conceptos[0] if conceptos else None

    fecha = root.get("Fecha", "")
    try:
        fecha_emision = datetime.fromisoformat(fecha)
    except ValueError as e:
        raise CfdiError(f"Fecha inválida: {fecha}") from e

    emisor_rfc = (emisor.get("Rfc") or "").upper()
    return Cfdi(
        uuid=uuid,
        company_id=company_id,
        tipo="emitido" if emisor_rfc == rfc_propio.upper() else "recibido",
        emisor_rfc=emisor_rfc,
        emisor_nombre=emisor.get("Nombre") or "",
        receptor_rfc=(receptor.get("Rfc") or "").upper(),
        receptor_nombre=receptor.get("Nombre") or "",
        total=_dec(root.get("Total")),
        subtotal=_dec(root.get("SubTotal")),
        iva=iva,
        fecha_emision=fecha_emision,
        concepto=concepto[:280],
        xml_path=xml_path,
        serie=root.get("Serie"),
        folio=root.get("Folio"),
        metodo_pago=root.get("MetodoPago"),
        forma_pago=root.get("FormaPago"),
        moneda=root.get("Moneda") or "MXN",
        uso_cfdi=receptor.get("UsoCFDI"),
        clave_prodserv=primero.get("ClaveProdServ") if primero is not None else None,
        clave_unidad=primero.get("ClaveUnidad") if primero is not None else None,
        n_conceptos=len(conceptos),
    )


def parsear_archivo(path: Path, company_id: str, rfc_propio: str,
                     base: Path | None = None) -> Cfdi:
    """Parsea un archivo .xml (xml_path relativo a `base` si se da)."""
    rel = str(path.relative_to(base)) if base else path.name
    return parsear_xml(path, company_id, rfc_propio, xml_path=rel)
