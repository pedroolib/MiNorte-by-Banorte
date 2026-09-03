"""Contrato Cfdi (base CFDI 4.0 simplificado) — source of truth (T0)."""

from datetime import datetime
from decimal import Decimal
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator

CfdiTipo = Literal["emitido", "recibido"]
CfdiStatus = Literal["vigente", "cancelado", "pendiente"]


class Cfdi(BaseModel):
    uuid: str = Field(examples=["12345678-1234-1234-1234-123456789012"])
    company_id: str = Field(examples=["company_001"])
    tipo: CfdiTipo
    emisor_rfc: str
    emisor_nombre: str
    receptor_rfc: str
    receptor_nombre: str
    total: Decimal = Field(gt=0)
    subtotal: Decimal = Field(gt=0)
    iva: Decimal = Field(ge=0, default=Decimal("0"))
    fecha_emision: datetime
    fecha_vencimiento: Optional[datetime] = None
    concepto: str = Field(examples=["Venta mostrador"])
    xml_path: Optional[str] = Field(
        default=None, examples=["seed/cfdis/emitido/A-1024.xml"]
    )
    status: CfdiStatus = "vigente"

    @field_validator("emisor_rfc", "receptor_rfc", mode="before")
    @classmethod
    def _upper_rfc(cls, v):
        return v.upper().strip() if isinstance(v, str) else v
