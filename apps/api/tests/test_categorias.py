"""Taxonomía T6: mapa SAT total, reglas banco y back-fill determinista."""

from decimal import Decimal
from pathlib import Path

from app.financial import categorias as cat
from app.integrations.banking.banorte_csv import cargar_csv
from app.integrations.sat import cfdi_xml as cx

REPO = Path(__file__).resolve().parents[3]
DIR = REPO / "seed" / "cfdis"


def test_sat_map_cubre_todo_el_seed():
    claves = set()
    for p in sorted(DIR.rglob("*.xml")):
        c = cx.parsear_archivo(p, "company_001", "CNM160812AB1", base=DIR)
        assert c.clave_prodserv, p.name  # todo XML trae clave
        claves.add(c.clave_prodserv)
    sin_mapeo = [k for k in claves if cat.rubro_por_clave(k) is None]
    assert not sin_mapeo, sin_mapeo
    assert cat.rubro_por_clave("72101500") == "servicios_generales"
    assert cat.rubro_por_clave("15101500") == "combustible"


def test_reglas_banco():
    R = cat.clasificar_rubro
    assert R("GASOL SANTA FE 640.10", "GASOL SANTA FE", "tarjeta", None, "egreso") == "combustible"
    assert R("COMPRA ORDEN DE PAGO SPEI Nomina 030323", "X", "spei_enviado") == "nomina"
    assert R("PAGO REFERENCIADO 123 Impuesto X", "X", "impuestos") == "impuestos"
    assert R("COMISION ORDEN DE PAGO SPEI", "BANORTE", "comision") == "comisiones_bancarias"
    assert R("TRASPASO A CUENTA DE TERCEROS ... AL R.F.C. X", "X", "traspaso_terceros") == "honorarios"
    assert R("CHEQUE PAGADO 0000224 ...", "X", "otro") == "varios"
    # CFDI manda sobre reglas banco
    assert R("COMPRA ORDEN DE PAGO SPEI Pago PO 1", "X", "spei_enviado",
             "78102200", "egreso") == "transporte_paqueteria"
    # ingresos: solo internos se tipifican
    assert R("SPEI RECIBIDO ... TRASPASO INTERNO", tipo="ingreso") == "traspaso_interno"
    assert R("SPEI RECIBIDO CLIENTE", tipo="ingreso") == "varios"


def test_loader_pone_rubro():
    txns = {t.id: t for t in cargar_csv(REPO / "seed" / "transactions.csv")}
    apple = next(t for t in txns.values() if t.merchant_name == "APPLE ONLINE STORE")
    assert apple.rubro == "equipo_computo"
    imp = next(t for t in txns.values() if t.categoria == "impuestos")
    assert imp.rubro == "impuestos"
    assert all(t.rubro != "" for t in txns.values())


def test_cobertura_seed():
    rows = [(r["descripcion"], r["comercio"], r["categoria"], None, r["tipo"])
            for r in __import__("csv").DictReader(
                open(REPO / "seed" / "transactions.csv", encoding="utf-8"))]
    rep = cat.cobertura(rows)
    assert rep["cobertura"] >= 0.95, rep["cobertura"]
    assert rep["total"] == 473


def test_normalizar_rubro_acepta_display():
    from app.financial.categorias import normalizar_rubro
    assert normalizar_rubro("Proveedores de materiales") == "proveedores_materiales"
    assert normalizar_rubro("Transporte Paquetería") == "transporte_paqueteria"
    assert normalizar_rubro("NOMINA") == "nomina"
    assert normalizar_rubro(None) is None
    try:
        normalizar_rubro("cohetes espaciales")
        assert False, "debió fallar"
    except ValueError as e:
        assert "proveedores_materiales" in str(e)


def test_merchants_acepta_display_y_enum():
    from app.mcp import tools as T
    a = T.execute("get_merchants", {"rubro": "Proveedores de materiales",
                                    "min_total": None, "limit": 200, "month": None})
    b = T.execute("get_merchants", {"rubro": "proveedores_materiales",
                                    "min_total": None, "limit": 200, "month": None})
    assert [r["nombre"] for r in a] == [r["nombre"] for r in b] and len(a) > 10
    schema = next(t["parameters"] for t in T.TOOLS if t["name"] == "get_merchants")
    assert "proveedores_materiales" in schema["properties"]["rubro"]["enum"]
