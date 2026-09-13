#!/usr/bin/env python3
"""Piloto: CFDIs falsos pareados con CSV real (determinista, privado).

Uso:
    uv run --project apps/api python scripts/build_pilot_cfdis.py \
      --csv seed/private/piloto/transactions_jul2026.csv \
      --outdir seed/private/piloto/cfdis \
      --company company_pilot \
      --emisor-rfc PIGP000101AB1 --emisor-nombre "PEDRO PISTONES GARCIA" \
      --emisor-regimen 612 --cp 21000 --serie PILOTO \
      --unpaid-n 5 --unpaid-seed 42

Reglas:
- Emitido pagado: 1 por cobro SPEI no-interno (total exacto, -5 días).
- Impagados: N clientes por RNG con seed fijo, montos = techo(millar)+500
  del propio cobro (garantizado distinto al banco), últimos días del mes.
- Recibidos: egresos conciliables (por nombre) salvo los 4 más chicos.
- Emisor/Receptor desconocido -> XAXX010101000 (público general, honesto).
- Todo marcado SIMULADO; UUIDs uuid5(piloto-...). Nada sale de private/.
- --match-all: ignora impagados/exclusiones; TODO movimiento no-interno
  lleva su CFDI (emitido=ingresos, recibido=egresos). Cero CxC simulada.
"""

from __future__ import annotations

import argparse
import csv
import random
import sys
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "apps" / "api"))

from app.integrations.sat.cfdi_build import cfdi_xml  # noqa: E402
from app.integrations.sat import cfdi_xml as cx  # noqa: E402

XAXX = "XAXX010101000"

CPS_POR_CATEGORIA = {
    "spei_enviado": ("72101500", "PAGO A PROVEEDOR POR SERVICIOS"),
    "traspaso_terceros": ("80101500", "PAGO A TERCERO POR SERVICIOS"),
    "cheque": ("72101500", "PAGO CON CHEQUE"),
    "domiciliacion": ("72101500", "SERVICIO DOMICILIADO"),
    "tarjeta": ("72101500", "COMPRA CON TARJETA"),
    "nomina": ("84111500", "PAGO DE NOMINA"),
    "impuestos": ("93151500", "PAGO DE IMPUESTOS Y DERECHOS"),
}


def concepto_emitido(comercio: str) -> tuple[str, str]:
    d = comercio.upper()
    if "TALLER" in d or "REFACC" in d or "BALATA" in d or "ACEITE" in d:
        return "31161500", "VENTA DE REFACCIONES"
    if "FLETE" in d or "TRANSPORTE" in d:
        return "78101800", "SERVICIO DE FLETE"
    return "72101500", "SERVICIO DE MANTENIMIENTO AUTOMOTRIZ"


def monto_impagado(cobro: Decimal, ocupados: set[str]) -> Decimal:
    base = (int(cobro // 1000) + 1) * 1000 + 500
    m = Decimal(base).quantize(Decimal("0.01"))
    while f"{m:.2f}" in ocupados:
        m += Decimal("1000.00")
    return m


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", required=True)
    ap.add_argument("--outdir", required=True)
    ap.add_argument("--company", required=True)
    ap.add_argument("--emisor-rfc", required=True)
    ap.add_argument("--emisor-nombre", required=True)
    ap.add_argument("--emisor-regimen", required=True)
    ap.add_argument("--cp", required=True)
    ap.add_argument("--serie", default="PILOTO")
    ap.add_argument("--unpaid-n", type=int, default=5)
    ap.add_argument("--unpaid-seed", type=int, default=42)
    ap.add_argument("--match-all", action="store_true",
                    help="CFDI para TODO movimiento no-interno (sin CxC "
                         "simulada ni exclusiones)")
    args = ap.parse_args()

    rows = list(csv.DictReader(open(args.csv, encoding="utf-8")))
    outdir = Path(args.outdir)
    (outdir / "emitido").mkdir(parents=True, exist_ok=True)
    (outdir / "recibido").mkdir(parents=True, exist_ok=True)
    for p in list((outdir / "emitido").glob("*.xml")) + list((outdir / "recibido").glob("*.xml")):
        p.unlink()
    montos_banco = {r["deposito"] for r in rows} | {r["retiro"] for r in rows}
    folio_e = folio_r = 1

    def guarda(sub: str, total: Decimal, **kw) -> Path:
        nonlocal folio_e, folio_r
        n = folio_e if sub == "emitido" else folio_r
        if sub == "emitido":
            folio_e += 1
        else:
            folio_r += 1
        p = outdir / sub / f"{args.serie}-{n:04d}.xml"
        p.write_text(cfdi_xml(serie=args.serie, folio=f"{n:04d}", **kw,
                              total=total, lugar=args.cp,
                              espacio_uuids=f"piloto-{sub}",
                              simulado=True), encoding="utf-8")
        return p

    # --- emitidos pagados ---
    if args.match_all:
        cobros = [r for r in rows
                  if r["tipo"] == "ingreso" and r["es_interno"] == "0"]
    else:
        cobros = [r for r in rows
                  if r["categoria"] == "spei_recibido" and r["es_interno"] == "0"]
    for r in cobros:
        cobro = date.fromisoformat(r["fecha"][:10])
        cps, concepto = concepto_emitido(r["comercio"])
        guarda("emitido", Decimal(r["deposito"]),
               fecha=(cobro - timedelta(days=5)).isoformat(), forma="03",
               emisor_rfc=args.emisor_rfc, emisor_nombre=args.emisor_nombre,
               emisor_reg=args.emisor_regimen, receptor_rfc=XAXX,
               receptor_nombre=r["comercio"], receptor_cp=args.cp,
               receptor_reg="612", uso="G03", cps=cps, concepto=concepto)
    n_pagados = len(cobros)

    # --- impagados: N clientes RNG (seed fijo), montos de su propio rango ---
    elegidos: list[str] = []
    total_cxc = Decimal("0")
    if args.match_all:
        print("match-all: sin CxC simulada")
    else:
        rng = random.Random(args.unpaid_seed)
        clientes = sorted({r["comercio"] for r in cobros
                           if len(r["comercio"]) >= 4})
        elegidos = rng.sample(clientes, min(args.unpaid_n, len(clientes)))
        import calendar as _cal
        ref = date.fromisoformat(max(r["fecha"][:10] for r in cobros))
        mes = date(ref.year, ref.month, _cal.monthrange(ref.year, ref.month)[1])
        for i, cli in enumerate(elegidos):
            propio = max(Decimal(r["deposito"]) for r in cobros
                         if r["comercio"] == cli)
            monto = monto_impagado(propio, montos_banco)
            montos_banco.add(f"{monto:.2f}")
            cps, concepto = concepto_emitido(cli)
            guarda("emitido", monto, fecha=(mes - timedelta(days=i)).isoformat(),
                   forma="03", emisor_rfc=args.emisor_rfc,
                   emisor_nombre=args.emisor_nombre,
                   emisor_reg=args.emisor_regimen, receptor_rfc=XAXX,
                   receptor_nombre=cli, receptor_cp=args.cp,
                   receptor_reg="612", uso="G03", cps=cps, concepto=concepto)
            total_cxc += monto

    # --- recibidos: conciliables salvo los 4 más chicos ---
    from app.financial.reconcile import es_conciliable
    from app.schemas.transaction import Transaction
    from datetime import datetime

    def _tx(r) -> Transaction:
        return Transaction(
            id=r["id"], company_id=args.company, account_id=r["account_id"],
            amount=Decimal(r["retiro"] or r["deposito"] or "0"), currency="MXN",
            date=datetime.fromisoformat(r["fecha"]), description=r["descripcion"],
            merchant_name=r["comercio"], merchant_rfc=r["rfc"] or None,
            type=r["tipo"], source=r.get("source") or "banorte_mock",
            es_interno=r["es_interno"] == "1", categoria=r["categoria"])

    if args.match_all:
        # TODO no-interno lleva CFDI: egresos (recibidos) sin excepciones.
        conc = [r for r in rows
                if r["tipo"] == "egreso" and r["es_interno"] == "0"]
        sin_ids: set[str] = set()
        print(f"match-all: recibidos para {len(conc)} egresos")
    else:
        conc = [r for r in rows if r["tipo"] == "egreso" and es_conciliable(_tx(r))]
        sin = sorted(conc, key=lambda r: (Decimal(r["retiro"]), r["id"]))[:4]
        sin_ids = {r["id"] for r in sin}
    n_rec = 0
    for r in conc:
        if r["id"] in sin_ids:
            continue
        cps, concepto = CPS_POR_CATEGORIA.get(
            r["categoria"], ("72101500", r["descripcion"][:80]))
        guarda("recibido", Decimal(r["retiro"]), fecha=r["fecha"][:10],
               forma="03", emisor_rfc=XAXX, emisor_nombre=r["comercio"],
               emisor_reg="612", receptor_rfc=args.emisor_rfc,
               receptor_nombre=args.emisor_nombre, receptor_cp=args.cp,
               receptor_reg=args.emisor_regimen, uso="G03",
               cps=cps, concepto=concepto)
        n_rec += 1

    # --- roundtrip por el parser REAL ---
    files = sorted(outdir.rglob("*.xml"))
    uuids = set()
    for p in files:
        c = cx.parsear_archivo(p, args.company, args.emisor_rfc, base=outdir)
        assert c.uuid not in uuids
        uuids.add(c.uuid)
        assert c.subtotal + c.iva == c.total
    print(f"emitidos={n_pagados + len(elegidos)} ({n_pagados} pagados + "
          f"{len(elegidos)} CxC=${total_cxc}) recibidos={n_rec}")
    if not args.match_all:
        print(f"4 sin factura suman "
              f"${sum((Decimal(r['retiro']) for r in sin), Decimal('0'))}")
    print(f"{len(files)} XMLs parsean OK, UUIDs únicos, SIMULADO marcado")


if __name__ == "__main__":
    main()
