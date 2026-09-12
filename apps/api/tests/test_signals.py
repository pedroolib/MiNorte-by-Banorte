"""Tests de signals(): catálogo general agnóstico sobre datos reales del seed.

Agosto 2026 (mes con historia previa) y junio 2026 (sin previo).
Valores verificados contra CSV + XMLs.
"""

from decimal import Decimal
from pathlib import Path

from app.financial import engine as en, reconcile as rc
from app.integrations.banking.banorte_csv import cargar_csv
from app.integrations.sat import cfdi_xml as cx

REPO = Path(__file__).resolve().parents[3]
TXNS = cargar_csv(REPO / "seed" / "transactions.csv")
CFDIS = [cx.parsear_archivo(p, "company_001", "CNM160812AB1", base=REPO / "seed" / "cfdis")
         for p in sorted((REPO / "seed" / "cfdis").rglob("*.xml"))]
MATCHES = rc.conciliar(TXNS, CFDIS)


def cerca(x, esperado, tol="0.002"):
    assert x is not None, f"esperaba {esperado}, fue None"
    assert abs(Decimal(str(x)) - Decimal(esperado)) < Decimal(tol), (x, esperado)


def S(a, m):
    return en.signals(TXNS, CFDIS, MATCHES, a, m)


def test_crecimiento_y_base_clientes():
    s = S(2026, 8)
    cerca(s["crec_ventas"], "0.4049")
    cerca(s["crec_gastos"], "0.3695")
    cerca(s["brecha_pp"], "-0.0354")
    assert s["ticket_mediano_ingreso"] == Decimal("3724.76")
    assert s["clientes_activos_mes"] == 5
    assert s["clientes_nuevos_mes"] == 4
    cerca(s["hhi_ingresos"], "0.4200")  # concentrado: pocos clientes


def test_rentabilidad_general():
    s = S(2026, 8)
    cerca(s["margen"], "-0.0200")
    cerca(s["margen_delta_pp"], "0.0264")
    cerca(s["margen_operativo_excl_comisiones"], "-0.0182")
    cerca(s["burn_multiple"], "0.0200")
    cerca(s["regla_40"], "0.3849")
    cerca(s["operating_leverage"], "0.9751")


def test_liquidez_general():
    s = S(2026, 8)
    assert s["burn_mensual"] == Decimal("8437.28")
    assert s["efectivo"] == Decimal("1294.68")
    assert s["runway_dias"] == 4
    cerca(s["cobertura_gastos_fijos"], "0.0514")
    assert (s["racha_signo"], s["racha_meses"]) == (-1, 3)  # 3 meses en burn
    assert s["volatilidad_flujo"] is not None and s["volatilidad_flujo"] > 0
    cerca(s["dso_dias"], "21.9782")


def test_fiscal_con_cfdi():
    s = S(2026, 8)
    assert s["iva_trasladado"] == Decimal("14412.41")
    assert s["iva_acreditable"] == Decimal("51288.81")
    assert s["iva_neto"] == Decimal("-36876.40")
    cerca(s["pct_gasto_deducible"], "0.9623")
    assert s["brecha_pagos_provision"] == Decimal("7611.00")


def test_comercial_y_estructura():
    s = S(2026, 8)
    assert s["cxc_total"] == Decimal("76550.00") and s["cxc_count"] == 5
    assert s["cxc_antiguedad_promedio_dias"] == 12.6
    assert s["cxc_pct_vencida"] == 0
    cerca(s["cxc_top_cliente"], "0.2782")
    cerca(s["hhi_gasto_proveedores"], "0.0931")
    assert s["fondeo_interno"] == Decimal("390000")
    cerca(s["ratio_fondeo_interno"], "0.9234")
    assert s["masa_salarial_estimada"] == Decimal("10542.50")
    assert s["gasto_por_categoria"]["spei_enviado"] > 0


def test_junio_sin_historia():
    s = S(2026, 6)
    for k in ("crec_ventas", "crec_gastos", "brecha_pp", "margen_previo",
              "margen_delta_pp", "regla_40", "operating_leverage"):
        assert s[k] is None, k
    assert s["runway_dias"] == 59
    assert s["cxc_count"] == 0 and s["dso_dias"] == 0
    assert s["clientes_nuevos_mes"] == s["clientes_activos_mes"] == 4


def test_signals_son_solo_datos():
    s = S(2026, 8)
    assert "severity" not in s and "titulo" not in s  # sin juicio
