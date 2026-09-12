"""Integración Supabase (sandbox company_test; nunca toca company_001).

Se salta sin credenciales o sin tablas (corre en CI igual).
Para correrlo: 001_core.sql aplicado + SUPABASE_URL/KEY en .env
+ `pytest apps/api/tests/test_supabase_repo.py -q`.
"""

from datetime import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest

from app.config import get_settings
from app.db import get_supabase
from app.repositories import transactions_repo as repo
from app.schemas.transaction import Transaction

SB = get_supabase()
COMPANY = "company_test"


def _tx(i: int) -> Transaction:
    return Transaction(
        id=f"test_{i}",
        company_id=COMPANY,
        account_id="acc_test",
        amount=Decimal("100.50"),
        currency="MXN",
        date=datetime(2026, 8, 1 + i, 12, tzinfo=ZoneInfo("America/Mexico_City")),
        description=f"MOVIMIENTO PRUEBA {i}",
        merchant_name="COMERCIO PRUEBA",
        type="egreso",
        balance=Decimal("900.00") - i * Decimal("100.50"),
        source="banorte_mock",
        categoria="tarjeta",
    )


@pytest.mark.skipif(SB is None, reason="sin Supabase")
def test_roundtrip_upsert_fetch():
    try:
        repo.count(SB, COMPANY)
    except Exception as e:
        if "PGRST205" in str(e) or "Could not find the table" in str(e):
            pytest.skip("tablas no creadas (corre 001_core.sql)")
        raise
    try:
        repo.upsert_company(SB, {
            "id": COMPANY, "rfc": "TEST010101T01",
            "razon_social": "EMPRESA PRUEBA SA DE CV",
        })
        repo.upsert_account(SB, {
            "company_id": COMPANY, "id": "acc_test", "alias": "Cuenta prueba",
        })
        assert repo.upsert_transactions(SB, [_tx(0), _tx(1)]) == 2
        # idempotencia: re-correr no duplica
        assert repo.upsert_transactions(SB, [_tx(0), _tx(1)]) == 2
        assert repo.count(SB, COMPANY) == 2
        got = repo.fetch_ordered(SB, COMPANY)
        assert [t.id for t in got] == ["test_0", "test_1"]
        assert got[0].amount == Decimal("100.50")
    finally:
        # limpieza sandbox (RLS demo lo permite; con auth se ajusta)
        SB.table("transactions").delete().eq("company_id", COMPANY).execute()
        SB.table("bank_accounts").delete().eq("company_id", COMPANY).execute()
        SB.table("companies").delete().eq("id", COMPANY).execute()
