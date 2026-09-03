"""MiNorte API — T0 esqueleto.

Solo expone:
- GET /health (para docker compose + frontend)
- GET /api/summary (mock con números objetivo del spec, el cálculo
  determinístico real llega en T4 Financial Engine)
"""

from datetime import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.schemas.financial import FinancialSummary

settings = get_settings()
MX_TZ = ZoneInfo(settings.TZ)

app = FastAPI(title=settings.APP_NAME, version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def get_current_company() -> str:
    """Single-company demo. TODO(auth): reemplazar por Supabase Auth."""
    return settings.COMPANY_ID


@app.get("/health")
def health():
    return {"status": "ok", "company_id": get_current_company()}


@app.get("/api/summary", response_model=FinancialSummary)
def api_summary():
    """Mock T0 con números objetivo del spec #4. T4 lo calculará de la DB."""
    return FinancialSummary(
        company_id=get_current_company(),
        ventas=Decimal("482300"),
        gastos=Decimal("410900"),
        utilidad=Decimal("71400"),
        efectivo=Decimal("184200"),
        impuesto_estimado=Decimal("32600"),
        cuentas_por_cobrar=Decimal("84500"),
        gastos_sin_cfdi_count=4,
        gastos_sin_cfdi_total=Decimal("8460"),
        updated_at=datetime.now(MX_TZ),
    )
