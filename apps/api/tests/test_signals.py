"""Tests de signals(): fórmulas estándar sobre datos reales del seed.

Valores de agosto 2026 verificados a mano contra el CSV:
ventas 422,364.67 / gastos 430,801.95 (julio 300,638.30 / 314,579.70).
"""

from decimal import Decimal
from pathlib import Path

from app.financial import engine as en
from app.integrations.banking.banorte_csv import cargar_csv

REPO = Path(__file__).resolve().parents[3]
TXNS = cargar_csv(REPO / "seed" / "transactions.csv")


def cerca(x, esperado, tol="0.002"):
    assert x is not None, f"esperaba {esperado}, fue None"
    assert abs(Decimal(x) - Decimal(esperado)) < Decimal(tol), (x, esperado)


def test_signals_agosto():
    s = en.signals(TXNS, 2026, 8)
    cerca(s["crec_ventas"], "0.4049")
    cerca(s["crec_gastos"], "0.3695")
    cerca(s["brecha_pp"], "-0.0355")
    cerca(s["margen"], "-0.0200")
    cerca(s["margen_delta_pp"], "0.0264")
    assert s["burn_mensual"] == Decimal("8437.28")
    assert s["efectivo"] == Decimal("1294.68")
    assert s["runway_dias"] == 4
    cerca(s["ratio_fondeo_interno"], "0.9233")
    assert s["fondeo_interno"] == Decimal("390000")
    cerca(s["operating_leverage"], "0.9750")
    assert s["gasto_por_categoria"]["spei_enviado"] > 0


def test_signals_junio_sin_previo():
    s = en.signals(TXNS, 2026, 6)
    assert s["crec_ventas"] is None and s["crec_gastos"] is None
    assert s["margen_previo"] is None and s["margen_delta_pp"] is None
    assert s["operating_leverage"] is None
    assert s["runway_dias"] == 59  # 23673.36 / (11876.58/30)
    assert s["efectivo"] == Decimal("23673.36")


def test_signals_son_solo_datos():
    s = en.signals(TXNS, 2026, 8)
    assert "severity" not in s and "titulo" not in s  # sin juicio
