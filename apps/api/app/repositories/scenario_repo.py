"""Repo escenarios guardados: simulaciones que vuelven al dashboard (T8)."""

import uuid
from typing import Any


def listar(sb: Any, company_id: str) -> list[dict]:
    try:
        return (sb.table("saved_scenarios").select("*")
                .eq("company_id", company_id)
                .order("created_at", desc=True).execute().data or [])
    except Exception:
        return []


def guardar(sb: Any, company_id: str, conversation_id: str | None,
            titulo: str, detalle: str, cifras: dict) -> dict:
    row = {"id": uuid.uuid4().hex[:8], "company_id": company_id,
           "conversation_id": conversation_id, "titulo": titulo,
           "detalle": detalle, "cifras": cifras}
    return (sb.table("saved_scenarios").insert(row).execute().data or [row])[0]
