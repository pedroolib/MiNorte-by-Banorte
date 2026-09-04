"""Operador cobranza (spec #3.3 caso 2): recordatorios de pago.

Flujo por factura (independiente: el lote es parcial por diseño):
  borrador -> [falta_email: pedir y guardar] -> [confirm] -> envío
  -> registro en collection_actions + last_reminder_at.

Nunca se aborta el lote: cada factura termina en
enviada | bloqueada_falta_email | omitida_24h | fallida.
"""

from __future__ import annotations

import re
from datetime import datetime

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def email_valido(email: str) -> bool:
    return bool(EMAIL_RE.match((email or "").strip()))


def _mxn(x) -> str:
    return f"${float(x):,.2f}"


def _fecha_corta(iso: str | None) -> str:
    return (iso or "")[:10] or "—"


def prepare_draft(receb: dict, cfdi: dict, contact: dict | None,
                  company: dict) -> dict:
    """Borrador del recordatorio con datos reales (factura + directorio)."""
    folio = f"{cfdi.get('serie') or ''}-{cfdi.get('folio') or ''}".strip("-")
    uuid = (cfdi.get("uuid") or "")[:8]
    body = (
        f"Hola, {receb.get('customer_name', '')}:\n\n"
        f"Te recordamos que la factura {folio} ({uuid}…) "
        f"por {_mxn(receb.get('amount_pending', 0))} continúa pendiente de pago.\n\n"
        f"Fecha de emisión: {_fecha_corta(receb.get('issued_at'))}\n"
        f"Fecha de vencimiento: {_fecha_corta(receb.get('due_date'))}\n"
        f"Importe pendiente: {_mxn(receb.get('amount_pending', 0))}\n\n"
        f"Agradecemos tu apoyo para realizar el pago o compartirnos "
        f"el estatus correspondiente.\n\n"
        f"Saludos,\n{company.get('nombre_comercial') or company.get('razon_social', '')}"
    )
    email = (contact or {}).get("email")
    return {
        "receivable_id": receb["id"],
        "to": email,
        "contact_status": "listo" if email_valido(email or "") else "falta_email",
        "subject": f"Recordatorio de pago — Factura {folio}",
        "body": body,
    }


def send_batch(drafts: list[dict], provider, ya_enviado,
               registrar, *, force: bool = False) -> list[dict]:
    """Envía un lote parcial. `ya_enviado(rid)->bool`, `registrar(item)->None`.

    Jamás aborta: cada item termina con su propio estado.
    """
    resultados: list[dict] = []
    for d in drafts:
        rid = d["receivable_id"]
        try:
            if not email_valido(d.get("to") or ""):
                resultados.append({**d, "status": "bloqueada_falta_email",
                                   "detail": "sin correo en el directorio"})
                continue
            if not force and ya_enviado(rid):
                registrar({**d, "status": "omitida_24h",
                           "detail": "ya se envió en las últimas 24h"})
                resultados.append({**d, "status": "omitida_24h",
                                   "detail": "ya se envió en las últimas 24h"})
                continue
            info = provider.send_email(to=d["to"], subject=d["subject"], body=d["body"])
            registrar({**d, "status": "enviada",
                       "detail": f"provider={provider.name} id={info.get('id')}"})
            resultados.append({**d, "status": "enviada",
                               "detail": f"id={info.get('id')}"})
        except Exception as e:  # noqa: BLE001 - el lote no se aborta
            try:
                registrar({**d, "status": "fallida", "detail": str(e)[:200]})
            finally:
                resultados.append({**d, "status": "fallida", "detail": str(e)[:200]})
    return resultados


def ahora_iso() -> str:
    return datetime.now().astimezone().isoformat()
