"""Contrato FinancialSummary — lo que pinta el dashboard (T0)."""

from datetime import datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, Field


class FinancialSummary(BaseModel):
    company_id: str = "company_001"
    ventas: Decimal = Field(ge=0)
    gastos: Decimal = Field(ge=0)
    utilidad: Decimal
    efectivo: Decimal
    impuesto_estimado: Decimal = Field(ge=0)
    cuentas_por_cobrar: Decimal = Field(ge=0)
    gastos_sin_cfdi_count: int = Field(ge=0)
    gastos_sin_cfdi_total: Decimal = Field(ge=0, default=Decimal("0"))
    updated_at: Optional[datetime] = None
