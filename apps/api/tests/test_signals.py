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
    cerca(s["hhi_gasto_proveedores"], "0.0760")  # nivel entidad, no cuenta
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


def test_brief_dice_lo_mismo_que_los_numeros():
    from app.financial import engine as en
    s = en.signals(TXNS, CFDIS, MATCHES, 2026, 8)
    b = "\n".join(en.brief_mensual(s, 2026, 8))
    assert "+40.5%" in b and "+37.0%" in b  # crecen, no decrecen
    assert "4 d" in b or "4 días" in b
    assert "0.0%" in b  # vencidas 0, explícito
    assert "422,364.67" in b


def test_mes_vacio_no_parece_caida():
    from app.financial import engine as en
    s = en.signals(TXNS, CFDIS, MATCHES, 2026, 9)
    assert s["tiene_datos"] is False and s["n_movimientos"] == 0
    b = en.brief_mensual(s, 2026, 9)
    assert any("SIN MOVIMIENTOS" in x for x in b)
    s8 = en.signals(TXNS, CFDIS, MATCHES, 2026, 8)
    assert s8["tiene_datos"] is True


def test_cxc_rfc_generico_fallback_a_nombre():
    """CFDIs generados por IA con XAXX compartido: la entidad es el nombre.
    Con el bug viejo (agrupar por RFC) top daría 1.0 con 2 clientes."""
    from datetime import datetime

    from app.schemas.cfdi import Cfdi

    def _cfdi(nombre, total, rfc="XAXX010101000"):
        return Cfdi(uuid=f"00000000-0000-4000-8000-00000000{total:04d}",
                    company_id="company_001", tipo="emitido",
                    emisor_rfc="CNM160812AB1", emisor_nombre="Café Norteño",
                    receptor_rfc=rfc, receptor_nombre=nombre,
                    total=Decimal(total), subtotal=Decimal(total),
                    iva=Decimal("0"),
                    fecha_emision=datetime(2026, 8, 10),
                    concepto="Venta")

    cfdis = [_cfdi("Cliente A", 3000), _cfdi("Cliente B", 1000)]
    s = en.signals([], cfdis, [], 2026, 8)
    assert s["cxc_count"] == 2 and s["cxc_total"] == Decimal("4000")
    cerca(s["cxc_top_cliente"], "0.75")  # 3000/4000 por nombre, no 1.0 por RFC


def test_cxc_rfc_real_manda_sobre_nombre():
    """Mismo cliente con 2 nombres pero RFC real: sigue siendo uno solo."""
    from datetime import datetime

    from app.schemas.cfdi import Cfdi

    def _cfdi(nombre, total):
        return Cfdi(uuid=f"11111111-1111-4000-8000-00000000{total:04d}",
                    company_id="company_001", tipo="emitido",
                    emisor_rfc="CNM160812AB1", emisor_nombre="Café Norteño",
                    receptor_rfc="CUPU800825569", receptor_nombre=nombre,
                    total=Decimal(total), subtotal=Decimal(total),
                    iva=Decimal("0"),
                    fecha_emision=datetime(2026, 8, 10),
                    concepto="Venta")

    cfdis = [_cfdi("CUPU Sucursal 1", 3000), _cfdi("CUPU Sucursal 2", 1000)]
    s = en.signals([], cfdis, [], 2026, 8)
    cerca(s["cxc_top_cliente"], "1.0")  # mismo RFC real = un cliente
