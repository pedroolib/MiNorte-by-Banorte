"""Repo de cfdis sobre Supabase (PostgREST). Upsert por (company_id, uuid)."""

from typing import Any

from app.schemas.cfdi import Cfdi


def _row(c: Cfdi) -> dict:
    return {
        "company_id": c.company_id,
        "uuid": c.uuid,
        "tipo": c.tipo,
        "emisor_rfc": c.emisor_rfc,
        "emisor_nombre": c.emisor_nombre,
        "receptor_rfc": c.receptor_rfc,
        "receptor_nombre": c.receptor_nombre,
        "total": str(c.total),
        "subtotal": str(c.subtotal),
        "iva": str(c.iva),
        "fecha_emision": c.fecha_emision.isoformat(),
        "fecha_vencimiento": c.fecha_vencimiento.isoformat() if c.fecha_vencimiento else None,
        "concepto": c.concepto,
        "xml_path": c.xml_path,
        "status": c.status,
        "serie": c.serie,
        "folio": c.folio,
        "metodo_pago": c.metodo_pago,
        "forma_pago": c.forma_pago,
        "moneda": c.moneda,
        "uso_cfdi": c.uso_cfdi,
        "clave_prodserv": c.clave_prodserv,
        "clave_unidad": c.clave_unidad,
        "lugar_expedicion": c.lugar_expedicion,
    }
def upsert_cfdis(sb: Any, cfdis: list[Cfdi], batch: int = 200) -> int:
    n = 0
    for i in range(0, len(cfdis), batch):
        chunk = [_row(c) for c in cfdis[i:i + batch]]
        sb.table("cfdis").upsert(chunk, on_conflict="company_id,uuid").execute()
        n += len(chunk)
    return n


def to_cfdi(r: dict, company_id: str) -> Cfdi:
    """Fila PostgREST -> contrato Cfdi."""
    return Cfdi(
        uuid=r["uuid"], company_id=company_id, tipo=r["tipo"],
        emisor_rfc=r["emisor_rfc"], emisor_nombre=r.get("emisor_nombre") or "",
        receptor_rfc=r["receptor_rfc"], receptor_nombre=r.get("receptor_nombre") or "",
        total=r["total"], subtotal=r["subtotal"], iva=r.get("iva") or 0,
        fecha_emision=r["fecha_emision"], fecha_vencimiento=r.get("fecha_vencimiento"),
        concepto=r.get("concepto") or "", xml_path=r.get("xml_path"),
        status=r.get("status") or "vigente", serie=r.get("serie"),
        folio=r.get("folio"), metodo_pago=r.get("metodo_pago"),
        forma_pago=r.get("forma_pago"), moneda=r.get("moneda") or "MXN",
        uso_cfdi=r.get("uso_cfdi"),
        clave_prodserv=r.get("clave_prodserv"),
        clave_unidad=r.get("clave_unidad"),
        lugar_expedicion=r.get("lugar_expedicion"),
    )


def fetch_all(sb: Any, company_id: str) -> list[Cfdi]:
    # Paginado: PostgREST topa en 1000 filas por request.
    out: list[Cfdi] = []
    off = 0
    while True:
        res = (
            sb.table("cfdis").select("*").eq("company_id", company_id)
            .order("fecha_emision").range(off, off + 999).execute()
        )
        filas = res.data or []
        out.extend(to_cfdi(r, company_id) for r in filas)
        if len(filas) < 1000:
            break
        off += 1000
    return out


def count(sb: Any, company_id: str, tipo: str | None = None) -> int:
    q = sb.table("cfdis").select("uuid", count="exact").eq("company_id", company_id)
    if tipo:
        q = q.eq("tipo", tipo)
    return q.execute().count or 0
