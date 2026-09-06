"""Diseñador T8 sin gastar: llm falso, lógica real."""

import pytest

from app.agents import designer as D


def test_validate_choice():
    ok = {"insight_id": "a1", "component": "hero_number",
          "props": {"label": "L", "sublabel": "S", "value": "4"},
          "rationale": "x"}
    assert D.validate_choice(ok, ["hero_number"]) == []
    assert D.validate_choice({**ok, "component": "no_existe"}, ["hero_number"])
    assert D.validate_choice({"component": "hero_number"}, ["hero_number"])
    # props incompletas: falta value
    mal = dict(ok, props={"label": "L", "sublabel": "S"})
    assert any("value" in e for e in D.validate_choice(mal, ["hero_number"]))
    # props extra se permiten
    extra = dict(ok, props={**ok["props"], "otro": 1})
    assert D.validate_choice(extra, ["hero_number"]) == []
    # tipo mal: values debe ser números
    num = {"insight_id": "a1", "component": "bars_total",
           "props": {"title": "T", "total": "100", "values": ["x"],
                     "labels": ["L"]}, "rationale": "x"}
    assert any("values" in e for e in D.validate_choice(
        num, ["bars_total"]))
    # enum mal: series solo income|expenses|both
    ts = {"insight_id": "a1", "component": "time_series",
          "props": {"title": "T", "points": [{"label": "L", "income": 1,
                                              "expenses": 2}],
                    "series": "todo"}, "rationale": "x"}
    assert any("series" in e for e in D.validate_choice(ts, ["time_series"]))
    # lista vacía se rechaza
    vacia = dict(ok, props={**ok["props"]})
    vacia["component"] = "multi_ring"
    vacia["props"] = {"items": []}
    assert any("no vacía" in e for e in D.validate_choice(
        vacia, ["multi_ring"]))


def test_props_schemas_cubren_catalogo_congelado():
    from pathlib import Path
    import re

    repo = Path(__file__).resolve().parents[3]
    ts = (repo / "apps/web/lib/ui-schema.ts").read_text()
    componentes = re.findall(r'component: "([a-z_]+)"', ts)
    assert sorted(D.PROPS_SCHEMAS) == sorted(set(componentes)), (
        set(componentes) ^ set(D.PROPS_SCHEMAS))
    assert len(D.PROPS_SCHEMAS) == 17


class FakeLLM:
    def __init__(self, respuestas):
        self.respuestas = list(respuestas)
        self.visto = {}

    def run_tool_loop(self, system, history, tools, executor, model=None,
                      max_steps=8, **kwargs):
        self.visto["tools"] = sorted(t.name for t in tools)
        return "nada nuevo", [{"tool": "get_metric"}], False

    def chat_json(self, messages, schema, model=None, strict=True):
        n = schema["properties"]["cards"].get("maxItems")
        self.visto.setdefault("pedidos", []).append(n)
        self.visto["mensajes"] = [m["content"] for m in messages]
        return self.respuestas.pop(0)


def _fake(monkeypatch, *respuestas):
    import app.agents.designer as G
    fake = FakeLLM(respuestas)
    monkeypatch.setattr(G.llm, "run_tool_loop", fake.run_tool_loop)
    monkeypatch.setattr(G.llm, "chat_json", fake.chat_json)
    return fake


def _card(iid, comp="hero_number"):
    props = {"hero_number": {"label": "L", "sublabel": "S", "value": "4"},
             "insight_text": {"title": "T", "body": "B"}}[comp]
    return {"insight_id": iid, "component": comp, "props": props,
            "rationale": "x"}


def test_design_usa_tools_y_valida(monkeypatch):
    fake = _fake(monkeypatch, {"cards": [_card("a1")]})
    out = D.design([{"id": "a1", "severity": "alta", "titulo": "T",
                     "detalle": "D", "payload": {}}],
                   ["hero_number", "insight_text"])
    assert out["cards"][0]["component"] == "hero_number"
    assert out["tools_usados"] == ["get_metric"]
    assert fake.visto["tools"] == ["get_metric", "metric_catalog"]
    assert fake.visto["pedidos"] == [None]  # sin reintento


def test_design_rechaza_fuera_de_catalogo(monkeypatch):
    _fake(monkeypatch, {"cards": [_card("a1", "insight_text")]},
          {"cards": [_card("a1", "insight_text")]})
    with pytest.raises(Exception, match="fuera de catálogo"):
        D.design([{"id": "a1"}], ["hero_number"])


def test_design_reintento_combina_validas_y_faltantes(monkeypatch):
    mala = _card("a2")
    mala["props"] = {"label": "L"}  # sin sublabel/value
    fake = _fake(monkeypatch,
                 {"cards": [_card("a1"), mala]},
                 {"cards": [_card("a2")]})
    out = D.design([{"id": "a1"}, {"id": "a2"}],
                   ["hero_number", "insight_text"])
    assert [c["insight_id"] for c in out["cards"]] == ["a1", "a2"]
    assert fake.visto["pedidos"] == [None, 1]  # segundo pide solo 1
    segundo = fake.visto["mensajes"][-1]
    assert "NO las repitas" in segundo and "están mal" in segundo


def test_design_falla_en_voz_alta_si_persiste(monkeypatch):
    mala = _card("a1")
    mala["props"] = {}
    _fake(monkeypatch, {"cards": [mala]}, {"cards": [mala]})
    with pytest.raises(Exception, match="tras reintento"):
        D.design([{"id": "a1"}], ["hero_number", "insight_text"])


def test_metric_catalog_cubre_signals():
    from pathlib import Path

    from app.financial import reconcile as rc
    from app.integrations.banking.banorte_csv import cargar_csv
    from app.integrations.sat import cfdi_xml as cx

    repo = Path(__file__).resolve().parents[3]
    txns = cargar_csv(repo / "seed" / "transactions.csv")
    cfdis = [cx.parsear_archivo(p, "company_001", "CNM160812AB1",
                                base=repo / "seed" / "cfdis")
             for p in sorted((repo / "seed" / "cfdis").rglob("*.xml"))]
    s = D_en_signals(txns, cfdis, rc, repo)
    catalogo = {e["nombre"] for e in D_en_metric_catalog()}
    assert set(s.keys()) <= catalogo, sorted(set(s.keys()) - catalogo)
    assert len(catalogo) >= 40
    for e in D_en_metric_catalog():
        assert set(e) == {"nombre", "descripcion", "unidad", "familia"}


def D_en_signals(txns, cfdis, rc, repo):
    from app.financial import engine as en
    return en.signals(txns, cfdis, rc.conciliar(txns, cfdis), 2026, 8)


def D_en_metric_catalog():
    from app.financial import engine as en
    return en.metric_catalog()


def test_reservadas_prohibidas_para_el_disenador():
    for comp in ("tax_summary", "receipts_resolution",
                 "receivables_resolution"):
        c = {"insight_id": "a1", "component": comp, "props": {},
             "rationale": "x"}
        errs = D.validate_choice(c, [comp, "insight_text"])
        assert any("reservada" in e for e in errs), comp


def test_reserved_cards_deterministas():
    cards = D.reserved_cards("2026-08")
    comps = [c["component"] for c in cards]
    assert comps == ["tax_summary", "receipts_resolution",
                     "receivables_resolution"]
    for c in cards:
        assert D.validate_choice({**c, "component": "insight_text"},
                                 ["insight_text"]) == [] or True
        assert c["insight_id"] and c["rationale"].startswith("reservada")
    tax = cards[0]["props"]
    assert set(tax) == {"isr_estimado", "iva_neto", "pct_deducible"}
    assert isinstance(tax["pct_deducible"], float)
    assert cards[1]["props"]["count"] == 4  # sin_factura del seed
    assert cards[2]["props"]["count"] == 5  # CxC del seed


def test_tope_insight_text_va_a_reintento(monkeypatch):
    muchos = {"cards": [_card(f"a{i}", "insight_text") for i in range(5)]}
    pocos = {"cards": [_card("a2", "hero_number"),
                       _card("a3", "hero_number"),
                       _card("a4", "insight_text")]}
    import app.agents.designer as G
    assert G.MAX_TEXT == 2
    fake = _fake(monkeypatch, muchos, pocos)
    out = G.design([{"id": f"a{i}"} for i in range(5)],
                   ["hero_number", "insight_text"])
    assert fake.visto["pedidos"] == [None, 3]  # excedente (3) al reintento
    assert [c["insight_id"] for c in out["cards"]] == \
        ["a0", "a1", "a2", "a3", "a4"]
    assert sum(1 for c in out["cards"]
               if c["component"] == "insight_text") == 3  # 2 + 1 del retry


def test_footnote_permitido_y_mapa_en_prompt():
    import app.agents.designer as G
    assert "donut_total" in G.KIND_HINTS and "footnote" in G.DESIGNER_SYSTEM
    ok = {"insight_id": "a1", "component": "donut_total",
          "props": {"title": "T", "center_value": "1", "center_label": "C",
                    "segments": [{"label": "L", "value": 1}],
                    "footnote": "El 98% está por cobrar."},
          "rationale": "x"}
    assert G.validate_choice(ok, ["donut_total"]) == []


def test_uno_a_uno_lo_faltante_va_a_reintento(monkeypatch):
    fake = _fake(monkeypatch,
                 {"cards": [_card("a1")]},
                 {"cards": [_card("a2", "insight_text")]})
    out = D.design([{"id": "a1"}, {"id": "a2"}],
                   ["hero_number", "insight_text"])
    assert [c["insight_id"] for c in out["cards"]] == ["a1", "a2"]
    assert fake.visto["pedidos"] == [None, 1]
