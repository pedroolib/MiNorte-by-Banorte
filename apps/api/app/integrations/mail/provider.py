"""MailProvider: el Operator no sabe qué servicio manda el correo (spec #21).

- LoggingMailProvider (default): registra y no envía. Para dev/tests/demo
  sin credenciales.
- ResendMailProvider: HTTP directo a api.resend.com (sin SDK extra).
  Requiere RESEND_API_KEY + MAIL_FROM (dominio verificado).
"""

from __future__ import annotations

import logging
from typing import Protocol

import httpx

from app.config import get_settings

log = logging.getLogger("minorte.mail")


class MailError(RuntimeError):
    pass


class MailProvider(Protocol):
    name: str

    def send_email(self, *, to: str, subject: str, body: str) -> dict:
        """Envía y devuelve {'id': ..., 'to': ...}. Lanza MailError si falla."""
        ...


class LoggingMailProvider:
    name = "log"

    def send_email(self, *, to: str, subject: str, body: str) -> dict:
        log.warning("[mail:log] to=%s subject=%s\n%s", to, subject, body)
        return {"id": f"log-{abs(hash((to, subject)))}", "to": to}


class ResendMailProvider:
    name = "resend"

    def __init__(self, api_key: str, from_addr: str):
        self.api_key = api_key
        self.from_addr = from_addr

    def send_email(self, *, to: str, subject: str, body: str) -> dict:
        try:
            r = httpx.post(
                "https://api.resend.com/emails",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={"from": self.from_addr, "to": [to],
                      "subject": subject, "text": body},
                timeout=20,
            )
        except Exception as e:
            raise MailError(f"resend red: {e}") from e
        if r.status_code >= 300:
            raise MailError(f"resend {r.status_code}: {r.text[:200]}")
        data = r.json()
        return {"id": data.get("id", ""), "to": to}


def get_mail_provider() -> MailProvider:
    s = get_settings()
    if s.MAIL_PROVIDER == "resend":
        if not s.RESEND_API_KEY or not s.MAIL_FROM:
            raise MailError("MAIL_PROVIDER=resend pero falta RESEND_API_KEY o MAIL_FROM")
        return ResendMailProvider(s.RESEND_API_KEY, s.MAIL_FROM)
    return LoggingMailProvider()
