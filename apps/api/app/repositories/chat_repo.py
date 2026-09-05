"""Repo agentes: conversaciones y solicitudes de crédito (T8)."""

import uuid
from typing import Any


def nueva_conversacion(sb: Any, company_id: str) -> dict:
    cid = uuid.uuid4().hex
    (sb.table("conversations").insert(
        {"id": cid, "company_id": company_id}).execute())
    return {"id": cid}


def get_conversacion(sb: Any, company_id: str, cid: str) -> dict | None:
    res = (sb.table("conversations").select("*").eq("id", cid)
           .eq("company_id", company_id).execute())
    return (res.data or [None])[0]


def historial(sb: Any, cid: str, limite: int = 10) -> list[dict]:
    res = (sb.table("messages").select("role,contenido")
           .eq("conversation_id", cid).order("created_at").execute())
    msgs = [{"role": ("user" if r["role"] == "usuario" else "assistant"),
             "content": r["contenido"]} for r in (res.data or [])]
    return msgs[-limite:]


def guardar_turno(sb: Any, cid: str, role: str, contenido: str,
                  tool_calls: list | None = None) -> None:
    (sb.table("messages").insert(
        {"id": uuid.uuid4().hex, "conversation_id": cid, "role": role,
         "contenido": contenido, "tool_calls": tool_calls or []}).execute())


def registrar_solicitud(sb: Any, company_id: str, terms: dict) -> dict:
    folio = "SOL-" + uuid.uuid4().hex[:8].upper()
    row = {"id": folio, "company_id": company_id,
           "option_id": terms["option_id"], "option_nombre": terms["nombre"],
           "amount": str(terms["amount"]), "months": terms["plazo_meses"],
           "tasa_anual": str(terms["tasa_anual"]),
           "pago_mensual": str(terms["pago_mensual"]),
           "costo_total": str(terms["costo_total"]),
           "cobertura": (str(terms["cobertura"]) if terms["cobertura"] is not None else None),
           "status": "solicitada_mock", "terms": terms}
    (sb.table("loan_applications").insert(row).execute())
    return {"folio": folio, **row}
