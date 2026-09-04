#!/usr/bin/env python3
"""Genera seed/cfdis/**/*.xml (CFDI 4.0 realistas) pareados con el banco.

Uso:
    uv run --project apps/api python scripts/build_seed_cfdis.py

Reglas de pareo (deterministas, montos 100% reales del CSV):
- EMITIDO pagado: uno por cada SPEI RECIBIDO no-interno (11). Total exacto
  al cobro, fecha = cobro - 5 días, folio A-1001...
- EMITIDO impagado (CxC demo): 5 ficticios con montos realistas del rango
  de cobros reales (6k-22k), agosto, vencimiento +30 días, folios A-1012...
- RECIBIDO pagado: uno por cada EGRESO con RFC identificable, EXCEPTO 4
  compras chicas con tarjeta que quedan sin factura (alerta Resolver T5).
  Sin RFC (impuestos, SPEI ND, comisiones) no lleva XML por definición.
- IVA 16%: subtotal = redondeo(total/1.16), iva = total - subtotal.
- UUID determinista (uuid5 por serie-folio): regenerar no cambia nada.

Todo ficticio salvo montos/fechas (estructura real del banco).
"""

from __future__ import annotations

import csv
import re
import sys
import uuid
from datetime import date, datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from xml.sax.saxutils import escape

REPO = Path(__file__).resolve().parents[1]
CSV = REPO / "seed" / "transactions.csv"
DIR = REPO / "seed" / "cfdis"

EMPRESA = "CAFE NORTENO SA DE CV"
RFC_PROPIO = "CNM160812AB1"
CP_PROPIO = "76087"

# 4 gastos con RFC que quedan SIN factura (alerta T5). Total real el que salga.
# (fecha, retiro, comercio) — estable contra el CSV.
SIN_FACTURA = [
    ("2026-07-27", "500.00", "MERCADO PAGO"),
    ("2026-06-16", "877.00", "MERCADO PAGO 1"),
    ("2026-08-16", "304.00", "FRANCISCO J. MORALES"),
    ("2026-08-27", "442.00", "SOFIA HERNANDEZ"),
]

# 5 emitidos impagados (CxC): (folio, cliente, rfc, total, emision)
# Montos realistas del rango de cobros reales (no forzados al placeholder).
IMPAGADOS = [
    ("A-1012", "CONSTRUCTORA VIA NORTE SA DE CV", "CVN190830M83", "18500.00", "2026-08-12"),
    ("A-1013", "DISTRIBUIDORA DEL NORTE SA DE CV", "DNO200415KX1", "12400.00", "2026-08-15"),
    ("A-1014", "TRANSPORTES DEL PACIFICO SA DE CV", "TPA180317G71", "21300.00", "2026-08-18"),
    ("A-1015", "COMERCIALIZADORA DEL BAJIO SA DE CV", "CBA170221B46", "8750.00", "2026-08-22"),
    ("A-1016", "PEDRO A. RUIZ", "MEDA950619KL6", "15600.00", "2026-08-25"),
]

CONCEPTOS_EMITIDO = [
    ("72101500", "SERVICIO DE MANTENIMIENTO INDUSTRIAL"),
    ("72101500", "SERVICIO DE SOLDADURA Y PAILERIA"),
    ("31161500", "VENTA DE REFACCIONES INDUSTRIALES"),
    ("78101800", "FLETE DE MATERIALES Y EQUIPO"),
    ("72101500", "SERVICIO DE INSTALACION ELECTRICA"),
    ("72101500", "SERVICIO DE REPARACION DE MAQUINARIA"),
]

CPS_DEFAULT = "72101500"


def cps_para(desc: str, categoria: str) -> tuple[str, str]:
    d = desc.upper()
    if "GASOL" in d:
        return "15101500", "COMPRA DE COMBUSTIBLE"
    if "SUPER" in d or "MERCADO PAGO" in d or "MERPAGO" in d:
        return "50161500", "COMPRA DE MATERIALES Y CONSUMIBLES"
    if "APPLE" in d:
        return "43211500", "COMPRA DE EQUIPO DE COMPUTO"
    if "DHL" in d or "PAQUETERIA" in d:
        return "78102200", "SERVICIO DE PAQUETERIA Y MENSAJERIA"
    if "ARREND" in d or "LEASING" in d or "VW " in d or "VOLKSWAGEN" in d:
        return "78111800", "ARRENDAMIENTO DE EQUIPO DE TRANSPORTE"
    if "RADIOMOVIL" in d or "TELCEL" in d or "TELMEX" in d or "CEL" in d:
        return "83111500", "SERVICIO DE TELEFONIA CELULAR"
    if "SEGUROS" in d:
        return "84131500", "PRIMA DE SEGUROS"
    if "ELECTRONICA" in d:
        return "32101500", "COMPRA DE COMPONENTES ELECTRONICOS"
    m = re.search(r"PAGO (?:A PROVEEDOR )?PO (\d+)", d)
    if m:
        return CPS_DEFAULT, f"PAGO A PROVEEDOR ORDEN {m.group(1)}"
    if categoria in ("spei_enviado", "traspaso_terceros"):
        return CPS_DEFAULT, "PAGO A PROVEEDOR POR SERVICIOS"
    return CPS_DEFAULT, "COMPRA DE MATERIALES Y CONSUMIBLES"


def partir_iva(total: Decimal) -> tuple[Decimal, Decimal]:
    sub = (total / Decimal("1.16")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return sub, total - sub


def cfdi_xml(*, serie: str, folio: str, fecha: str, forma: str,
             emisor_rfc: str, emisor_nombre: str, emisor_reg: str,
             receptor_rfc: str, receptor_nombre: str, receptor_cp: str,
             receptor_reg: str, uso: str, cps: str, concepto: str,
             total: Decimal, lugar: str = CP_PROPIO) -> str:
    sub, iva = partir_iva(total)
    uid = str(uuid.uuid5(uuid.NAMESPACE_URL, f"minorte-{serie}-{folio}")).upper()
    hora = f"{fecha}T12:00:00"
    timbrado = f"{fecha}T12:05:00"
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<cfdi:Comprobante xmlns:cfdi="http://www.sat.gob.mx/cfd/4" xmlns:tfd="http://www.sat.gob.mx/TimbreFiscalDigital" Version="4.0" Serie="{serie}" Folio="{folio}" Fecha="{hora}" FormaPago="{forma}" SubTotal="{sub:.2f}" Moneda="MXN" Total="{total:.2f}" TipoDeComprobante="I" MetodoPago="PUE" LugarExpedicion="{lugar}" Exportacion="01">
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


def regimen(rfc: str) -> str:
    return "601" if len(rfc) == 12 else "612"


def main() -> None:
    rows = list(csv.DictReader(open(CSV, encoding="utf-8")))
    (DIR / "emitido").mkdir(parents=True, exist_ok=True)
    (DIR / "recibido").mkdir(parents=True, exist_ok=True)
    for p in list((DIR / "emitido").glob("*.xml")) + list((DIR / "recibido").glob("*.xml")):
        p.unlink()

    rfc_nombre: dict[str, str] = {}
    for r in rows:
        if r["rfc"]:
            rfc_nombre.setdefault(r["rfc"], r["comercio"])
    montos_banco = {r["deposito"] for r in rows} | {r["retiro"] for r in rows}

    n_emi = n_rec = 0
    # --- emitidos pagados: 1 por cobro no-interno ---
    folio = 1001
    for i, r in enumerate([x for x in rows if x["categoria"] == "spei_recibido" and x["es_interno"] == "0"]):
        cobro = date.fromisoformat(r["fecha"][:10])
        emision = max(cobro - timedelta(days=5), date(2026, 6, 1))
        cps, concepto = CONCEPTOS_EMITIDO[i % len(CONCEPTOS_EMITIDO)]
        cp = {"CVN190830M83": "76080"}.get(r["rfc"], CP_PROPIO)
        (DIR / "emitido" / f"A-{folio}.xml").write_text(cfdi_xml(
            serie="A", folio=str(folio), fecha=emision.isoformat(), forma="03",
            emisor_rfc=RFC_PROPIO, emisor_nombre=EMPRESA, emisor_reg="601",
            receptor_rfc=r["rfc"], receptor_nombre=r["comercio"],
            receptor_cp=cp, receptor_reg=regimen(r["rfc"]), uso="G03",
            cps=cps, concepto=concepto, total=Decimal(r["deposito"])), encoding="utf-8")
        folio += 1
        n_emi += 1

    # --- emitidos impagados (CxC demo) ---
    total_cxc = Decimal("0")
    for fol, cli, rfc, total, emision in IMPAGADOS:
        assert total not in montos_banco, f"impagado {fol} colisiona con banco"
        cps, concepto = CONCEPTOS_EMITIDO[hash(fol) % len(CONCEPTOS_EMITIDO)]
        serie, num = fol.split("-")
        (DIR / "emitido" / f"{fol}.xml").write_text(cfdi_xml(
            serie=serie, folio=num, fecha=emision, forma="03",
            emisor_rfc=RFC_PROPIO, emisor_nombre=EMPRESA, emisor_reg="601",
            receptor_rfc=rfc, receptor_nombre=cli,
            receptor_cp=CP_PROPIO, receptor_reg=regimen(rfc), uso="G03",
            cps=cps, concepto=concepto, total=Decimal(total)), encoding="utf-8")
        total_cxc += Decimal(total)
        n_emi += 1

    # --- recibidos: todo egreso con RFC salvo los 4 sin factura ---
    # (comisiones/IVA bancarios no llevan XML individual: el banco factura
    # el paquete mensual; T5 los excluye por categoría)
    sin = {(f, m, c) for f, m, c in SIN_FACTURA}
    serie_i = 2001
    total_sin = Decimal("0")
    for r in rows:
        if r["tipo"] != "egreso" or not r["rfc"]:
            continue
        if r["categoria"] in ("comision", "iva_comision"):
            continue
        key = (r["fecha"][:10], r["retiro"], r["comercio"])
        if key in sin:
            total_sin += Decimal(r["retiro"])
            continue
        cps, concepto = cps_para(r["descripcion"], r["categoria"])
        serie = {"tarjeta": "T", "domiciliacion": "D"}.get(r["categoria"], "F")
        (DIR / "recibido" / f"{serie}-{serie_i}.xml").write_text(cfdi_xml(
            serie=serie, folio=str(serie_i), fecha=r["fecha"][:10], forma="04" if r["categoria"] == "tarjeta" else "03",
            emisor_rfc=r["rfc"], emisor_nombre=r["comercio"], emisor_reg=regimen(r["rfc"]),
            receptor_rfc=RFC_PROPIO, receptor_nombre=EMPRESA,
            receptor_cp=CP_PROPIO, receptor_reg="601", uso="G03",
            cps=cps, concepto=concepto, total=Decimal(r["retiro"])), encoding="utf-8")
        serie_i += 1
        n_rec += 1

    print(f"emitidos={n_emi} (11 pagados + 5 CxC=${total_cxc}) recibidos={n_rec}")
    print(f"4 sin factura suman ${total_sin}")


if __name__ == "__main__":
    main()
