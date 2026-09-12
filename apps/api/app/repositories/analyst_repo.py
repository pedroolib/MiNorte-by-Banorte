"""Repo Analista: insights rankeados por (company, mes) (T8)."""

from typing import Any


_ORDEN = {"critical": 0, "warning": 1, "info": 2}


def listar(sb: Any, company_id: str, month: str) -> list[dict]:
    filas = (sb.table("analyst_insights").select("*")
             .eq("company_id", company_id).eq("month", month)
             .order("created_at").execute().data or [])
    # Orden por urgencia en Python: PostgREST no ordena por CASE.
    filas.sort(key=lambda f: (_ORDEN.get(f.get("severity"), 9),
                              f.get("created_at", "")))
    return filas


def reemplazar(sb: Any, company_id: str, month: str,
               insights: list[dict]) -> list[dict]:
    """Idempotente: borra el mes y guarda los nuevos (conservar id uuid app)."""
    (sb.table("analyst_insights").delete()
     .eq("company_id", company_id).eq("month", month).execute())
    if insights:
        (sb.table("analyst_insights").insert(insights).execute())
    return listar(sb, company_id, month)


def guardar_anchors(sb: Any, company_id: str, month: str,
                    anchors: list[dict]) -> list[dict]:
    """Comentarios de anclas del mes (idempotente por métrica)."""
    for a in anchors:
        (sb.table("analyst_anchors")
         .upsert({"company_id": company_id, "month": month,
                  "metric": a["metric"], "comment": a["comment"]},
                 on_conflict="company_id,month,metric").execute())
    return listar_anchors(sb, company_id, month)


def listar_anchors(sb: Any, company_id: str, month: str) -> list[dict]:
    return (sb.table("analyst_anchors").select("*")
            .eq("company_id", company_id).eq("month", month)
            .execute().data or [])
