"""Constructor de CFDI 4.0 para SEED (mock honesto, spec #13).

La frontera mock es *cómo llegó el XML*: estos archivos simulan la
recepción/sincronización. El parseo posterior (cfdi_xml.py) es real.
Con simulado=True se marca el XML como sin validez fiscal.
"""

from __future__ import annotations

import uuid
from decimal import Decimal, ROUND_HALF_UP
from xml.sax.saxutils import escape


def partir_iva(total: Decimal) -> tuple[Decimal, Decimal]:
    sub = (total / Decimal("1.16")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return sub, total - sub


def regimen(rfc: str) -> str:
    return "601" if len(rfc) == 12 else "612"


def cfdi_xml(*, serie: str, folio: str, fecha: str, forma: str,
             emisor_rfc: str, emisor_nombre: str, emisor_reg: str,
             receptor_rfc: str, receptor_nombre: str, receptor_cp: str,
             receptor_reg: str, uso: str, cps: str, concepto: str,
             total: Decimal, lugar: str,
             espacio_uuids: str = "minorte", simulado: bool = False) -> str:
    sub, iva = partir_iva(total)
    uid = str(uuid.uuid5(uuid.NAMESPACE_URL,
                         f"{espacio_uuids}-{serie}-{folio}")).upper()
    hora = f"{fecha}T12:00:00"
    timbrado = f"{fecha}T12:05:00"
    marca = ("<!-- SIMULADO PARA DEMO: sin validez fiscal -->\n"
             if simulado else "")
    return f"""<?xml version="1.0" encoding="UTF-8"?>
{marca}<cfdi:Comprobante xmlns:cfdi="http://www.sat.gob.mx/cfd/4" xmlns:tfd="http://www.sat.gob.mx/TimbreFiscalDigital" Version="4.0" Serie="{serie}" Folio="{folio}" Fecha="{hora}" FormaPago="{forma}" SubTotal="{sub:.2f}" Moneda="MXN" Total="{total:.2f}" TipoDeComprobante="I" MetodoPago="PUE" LugarExpedicion="{lugar}" Exportacion="01">
 <cfdi:Emisor Rfc="{emisor_rfc}" Nombre="{escape(emisor_nombre)}" RegimenFiscal="{emisor_reg}"/>
 <cfdi:Receptor Rfc="{receptor_rfc}" Nombre="{escape(receptor_nombre)}" DomicilioFiscalReceptor="{receptor_cp}" RegimenFiscalReceptor="{receptor_reg}" UsoCFDI="{uso}"/>
 <cfdi:Conceptos>
  <cfdi:Concepto ClaveProdServ="{cps}" Cantidad="1" ClaveUnidad="E48" Descripcion="{escape(concepto)}" ValorUnitario="{sub:.2f}" Importe="{sub:.2f}"/>
 </cfdi:Conceptos>
 <cfdi:Impuestos TotalImpuestosTrasladados="{iva:.2f}">
  <cfdi:Traslados>
   <cfdi:Traslado Base="{sub:.2f}" Impuesto="002" TipoFactor="Tasa" TasaOCuota="0.160000" Importe="{iva:.2f}"/>
  </cfdi:Traslados>
 </cfdi:Impuestos>
 <cfdi:Complemento>
  <tfd:TimbreFiscalDigital Version="1.1" UUID="{uid}" FechaTimbrado="{timbrado}" RfcProvCertif="SAT970701NN3"/>
 </cfdi:Complemento>
</cfdi:Comprobante>
"""
