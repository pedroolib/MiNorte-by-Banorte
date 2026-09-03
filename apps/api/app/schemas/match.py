"""Contrato Match (reconciliación) — source of truth (T0).

Fórmula (spec #17, se implementa en T5):
score = amount*0.50 + date*0.20 + merchant*0.30
>=0.85 auto, 0.60-0.85 review, <0.60 unmatched
"""

from decimal import Decimal
from typing import Literal, Optional

from pydantic import BaseModel, Field

MatchStatus = Literal["auto", "review", "unmatched"]


class Match(BaseModel):
    transaction_id: str
    cfdi_id: Optional[str] = None
    score: Decimal = Field(ge=0, le=1)
    amount_score: Decimal = Field(ge=0, le=1)
    date_score: Decimal = Field(ge=0, le=1)
    merchant_score: Decimal = Field(ge=0, le=1)
    status: MatchStatus
