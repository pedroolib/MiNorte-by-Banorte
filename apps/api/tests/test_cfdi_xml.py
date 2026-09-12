"""Tests del parser CFDI 4.0 (fixtures ficticias, sin PII)."""

from decimal import Decimal

import pytest

from app.integrations.sat import cfdi_xml as cx

PROPIO = "CNM160812AB1"


def xml_emitido() -> str:
    return """<?xml version="1.0" encoding="UTF-8"?>
<cfdi:Comprobante xmlns:cfdi="http://www.sat.gob.mx/cfd/4" xmlns:tfd="http://www.sat.gob.mx/TimbreFiscalDigital"
 Version="4.0" Serie="A" Folio="1001" Fecha="2026-05-28T12:00:00" FormaPago="03"
 SubTotal="8500.00" Moneda="MXN" Total="9860.00" TipoDeComprobante="I" MetodoPago="PUE"
 LugarExpedicion="76087" Exportacion="01">
 <cfdi:Emisor Rfc="CNM160812AB1" Nombre="CAFE NORTENO SA DE CV" RegimenFiscal="601"/>
 <cfdi:Receptor Rfc="CVN190830M83" Nombre="CONSTRUCTORA VIA NORTE SA DE CV"
  DomicilioFiscalReceptor="76080" RegimenFiscalReceptor="601" UsoCFDI="G03"/>
 <cfdi:Conceptos>
  <cfdi:Concepto ClaveProdServ="72101500" Cantidad="1" ClaveUnidad="E48"
   Descripcion="SERVICIO DE MANTENIMIENTO INDUSTRIAL" ValorUnitario="8500.00" Importe="8500.00"/>
 </cfdi:Conceptos>
 <cfdi:Impuestos TotalImpuestosTrasladados="1360.00">
  <cfdi:Traslados>
   <cfdi:Traslado Base="8500.00" Impuesto="002" TipoFactor="Tasa" TasaOCuota="0.160000" Importe="1360.00"/>
  </cfdi:Traslados>
 </cfdi:Impuestos>
 <cfdi:Complemento>
  <tfd:TimbreFiscalDigital Version="1.1" UUID="AAAAAAAA-1111-4B22-8C33-123456789012"
   FechaTimbrado="2026-05-28T12:05:00" RfcProvCertif="SAT970701NN3"/>
 </cfdi:Complemento>
</cfdi:Comprobante>"""


def test_emitidoCompleto():
    c = cx.parsear_xml(xml_emitido(), "company_001", PROPIO, xml_path="seed/x.xml")
    assert c.tipo == "emitido"
    assert c.uuid == "AAAAAAAA-1111-4B22-8C33-123456789012"
    assert c.emisor_rfc == PROPIO
    assert c.receptor_rfc == "CVN190830M83"
    assert c.total == Decimal("9860.00")
    assert c.subtotal == Decimal("8500.00")
    assert c.iva == Decimal("1360.00")
    assert c.subtotal + c.iva == c.total
    assert c.serie == "A" and c.folio == "1001"
    assert c.metodo_pago == "PUE" and c.forma_pago == "03"
    assert c.uso_cfdi == "G03"
    assert "MANTENIMIENTO" in c.concepto


def test_recibidoSeDetectaPorRfc():
    x = xml_emitido().replace('Rfc="CNM160812AB1"', 'Rfc="PRO999999XX9"', 1)
    c = cx.parsear_xml(x, "company_001", PROPIO)
    assert c.tipo == "recibido"
    assert c.emisor_rfc == "PRO999999XX9"


def test_errores_claros():
    with pytest.raises(cx.CfdiError):
        cx.parsear_xml("<no-xml", "company_001", PROPIO)
    with pytest.raises(cx.CfdiError):
        cx.parsear_xml("<cfdi:Comprobante/>", "company_001", PROPIO)
    sin_timbre = xml_emitido().split("<cfdi:Complemento>")[0] + "</cfdi:Comprobante>"
    with pytest.raises(cx.CfdiError):
        cx.parsear_xml(sin_timbre, "company_001", PROPIO)
