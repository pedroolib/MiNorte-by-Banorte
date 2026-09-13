"""Repo tickets: documentos subidos + solicitudes de factura (spec #14).

Tablas `documents` e `invoice_requests` (migración 013). Mismo patrón que
`collections_repo.py`: PostgREST directo, sin ORM.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def create_document(sb: Any, company_id: str, mime: str,
                    extraction: dict, storage_path: str | None = None,
                    kind: str = "receipt") -> dict:
    row = {"company_id": company_id, "kind": kind, "mime": mime,
           "storage_path": storage_path, "extraction": extraction}
    res = sb.table("documents").insert(row).execute()
    return res.data[0]


def get_document(sb: Any, company_id: str, document_id: str) -> dict | None:
    res = (sb.table("documents").select("*").eq("company_id", company_id)
           .eq("id", document_id).execute())
    return (res.data or [None])[0]


def create_invoice_request(sb: Any, company_id: str, document_id: str,
                           transaction_id: str | None, payload: dict,
                           status: str = "borrador") -> dict:
    row = {"company_id": company_id, "document_id": document_id,
           "transaction_id": transaction_id, "payload": payload,
           "status": status, "steps": []}
    res = sb.table("invoice_requests").insert(row).execute()
    return res.data[0]


def get_invoice_request(sb: Any, company_id: str, invoice_id: str) -> dict | None:
    res = (sb.table("invoice_requests").select("*").eq("company_id", company_id)
           .eq("id", invoice_id).execute())
    return (res.data or [None])[0]


def list_invoice_requests(sb: Any, company_id: str) -> list[dict]:
    return (sb.table("invoice_requests").select("*").eq("company_id", company_id)
            .order("created_at", desc=True).execute().data or [])


def update_invoice_request(sb: Any, company_id: str, invoice_id: str,
                           fields: dict) -> dict | None:
    fields = {**fields, "updated_at": datetime.now(timezone.utc).isoformat()}
    (sb.table("invoice_requests").update(fields).eq("company_id", company_id)
     .eq("id", invoice_id).execute())
    return get_invoice_request(sb, company_id, invoice_id)
