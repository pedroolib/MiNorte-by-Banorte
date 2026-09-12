"""Contrato Transaction — source of truth (T0).

Convenciones T0:
- MXN con Decimal (nunca float para dinero).
- Fechas ISO 8601 con zona America/Mexico_City.
- RFC en mayúsculas.
"""

from datetime import datetime
from decimal import Decimal
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator

TransactionType = Literal["ingreso", "egreso"]
TransactionSource = Literal["banorte_mock", "banorte_real", "bbva_mock", "manual"]


class Transaction(BaseModel):
    id: str = Field(examples=["txn_0001"])
    company_id: str = Field(examples=["company_001"])
    account_id: str = Field(examples=["acc_eje_001"])
    amount: Decimal = Field(gt=0, examples=["1250.50"])
    currency: Literal["MXN"] = "MXN"
    date: datetime = Field(examples=["2026-08-12T14:30:00-06:00"])
    description: str = Field(examples=["OXXO SUC 123 MTY"])
    merchant_name: str = Field(examples=["OXXO"])
    merchant_rfc: Optional[str] = Field(default=None, examples=["OMX140726U5A"])
    type: TransactionType
    balance: Optional[Decimal] = None
    source: TransactionSource = "banorte_mock"
    # Traspasos entre cuentas propias: se excluyen de ventas/gastos (T4).
    es_interno: bool = False
    # Categoría heurística (banorte_csv.clasificar). T4 la refina.
    categoria: str = "otro"
    # Rubro de gasto PyME (financial/categorias.py). Back-fill desde CFDI.
    rubro: str = "por_clasificar"

    @field_validator("merchant_rfc", mode="before")
    @classmethod
    def _upper_rfc(cls, v):
        return v.upper().strip() if isinstance(v, str) else v
