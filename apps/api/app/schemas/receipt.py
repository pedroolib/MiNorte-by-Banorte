"""Contrato Ticket/Factura (spec #3.3 caso 1, #14, #19) — source of truth.

Documento = la foto subida + lo que Vision pudo leer (nunca calcula).
InvoiceRequest = el estado del flujo ticket -> match -> browser agent -> CFDI.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field

InvoiceRequestStatus = Literal[
    "borrador",
    "listo_para_portal",
    "navegando",
    "esperando_confirmacion",
    "bloqueada_captcha",
    "bloqueada_auth",
    "bloqueada_datos_faltantes",
    "bloqueada_limite_pasos",
    "cancelada",
    "resuelta",
    "fallida",
]


class ReceiptExtraction(BaseModel):
    """Lo que Vision pudo leer del ticket. Campo no legible = null, nunca
    inventado (spec #18: el motor/la IA no inventan cifras)."""

    comercio: Optional[str] = None
    rfc_comercio: Optional[str] = None
    total: Optional[Decimal] = None
    fecha: Optional[datetime] = None
    folio: Optional[str] = None
    portal_facturacion: Optional[str] = None
    confianza: Literal["alta", "media", "baja"] = "baja"
    campos_no_legibles: list[str] = Field(default_factory=list)


class MatchCandidate(BaseModel):
    """Candidato de conciliación ticket<->movimiento (misma fórmula que
    `financial/reconcile.py`, spec #17), para que el usuario confirme."""

    transaction_id: str
    score: Decimal
    amount_score: Decimal
    date_score: Decimal
    merchant_score: Decimal
    merchant_name: str
    amount: Decimal
    date: datetime


class Document(BaseModel):
    id: str
    company_id: str
    kind: Literal["receipt"] = "receipt"
    mime: str = "image/jpeg"
    storage_path: Optional[str] = None
    extraction: dict[str, Any] = Field(default_factory=dict)
    created_at: Optional[datetime] = None


class InvoiceRequest(BaseModel):
    id: str
    company_id: str
    document_id: str
    transaction_id: Optional[str] = None
    payload: dict[str, Any] = Field(default_factory=dict)
    status: InvoiceRequestStatus = "borrador"
    steps: list[dict[str, Any]] = Field(default_factory=list)
    cfdi_uuid: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
