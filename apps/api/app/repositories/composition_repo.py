"""Repo Composición: memoria de exposición semanal (T8)."""

import uuid
from typing import Any


def registrar(sb: Any, company_id: str, week_id: str,
              items: list[dict]) -> int:
    """Guarda qué se mostró (kind + fingerprint + posición). Idempotente
    por semana: regenerar la misma semana reemplaza su memoria."""
    (sb.table("insight_exposures").delete()
     .eq("company_id", company_id).eq("week_id", week_id).execute())
    filas = [{"id": uuid.uuid4().hex[:8], "company_id": company_id,
              "week_id": week_id, "insight_kind": it["kind"],
              "insight_fingerprint": it.get("fingerprint", ""),
              "position": pos}
             for pos, it in enumerate(items)]
    if filas:
        sb.table("insight_exposures").insert(filas).execute()
    return len(filas)


def historial(sb: Any, company_id: str) -> list[dict]:
    """Exposiciones recientes (para novelty / repetition_penalty)."""
    try:
        return (sb.table("insight_exposures").select("*")
                .eq("company_id", company_id)
                .order("shown_at", desc=True).limit(200).execute().data or [])
    except Exception:
        return []


def composicion_semana(sb: Any, company_id: str,
                       week_id: str) -> list[dict]:
    """Memoria de una semana (para idempotencia del dashboard)."""
    try:
        return (sb.table("insight_exposures").select("*")
                .eq("company_id", company_id).eq("week_id", week_id)
                .order("position").execute().data or [])
    except Exception:
        return []


def guardar_composicion(sb: Any, company_id: str, week_id: str,
                        month: str, payload: dict) -> None:
    """JSON final por semana (el GET lo devuelve sin regenerar)."""
    (sb.table("dashboard_compositions")
     .upsert({"company_id": company_id, "week_id": week_id,
              "month": month, "payload": payload},
             on_conflict="company_id,week_id").execute())


def leer_composicion(sb: Any, company_id: str,
                     week_id: str) -> dict | None:
    try:
        filas = (sb.table("dashboard_compositions").select("*")
                 .eq("company_id", company_id).eq("week_id", week_id)
                 .execute().data or [])
        return filas[0]["payload"] if filas else None
    except Exception:
        return None
