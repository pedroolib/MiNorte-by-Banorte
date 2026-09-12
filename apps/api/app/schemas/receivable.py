"""Contrato Receivable (cuentas por cobrar) — source of truth (T0)."""

from datetime import datetime
from decimal import Decimal
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator, model_validator

ReceivableStatus = Literal["open", "partially_paid", "paid", "overdue"]


class Receivable(BaseModel):
    id: str = Field(examples=["ar_0001"])
    company_id: str = Field(examples=["company_001"])
    cfdi_id: str = Field(examples=["12345678-1234-1234-1234-123456789012"])
    customer_name: str
    customer_rfc: str
    amount: Decimal = Field(gt=0)
    amount_paid: Decimal = Field(ge=0, default=Decimal("0"))
    amount_pending: Optional[Decimal] = None
    issued_at: datetime
    due_date: Optional[datetime] = None
    status: ReceivableStatus = "open"
    last_reminder_at: Optional[datetime] = None

    @field_validator("customer_rfc", mode="before")
    @classmethod
    def _upper_rfc(cls, v):
        return v.upper().strip() if isinstance(v, str) else v

    @model_validator(mode="after")
    def _pending(self):
        if self.amount_pending is None:
            self.amount_pending = self.amount - self.amount_paid
        return self
