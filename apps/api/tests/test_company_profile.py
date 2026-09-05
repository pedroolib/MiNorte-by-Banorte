"""Perfil del negocio: detección, validación, endpoints y contexto IA."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import app.main as main
from app.integrations.banking.banorte_csv import cargar_csv
from app.integrations.sat import cfdi_xml as cx
from app.repositories import profile_repo

REPO = Path(__file__).resolve().parents[3]


def test_sugerencia_datos_reales():
    txns = cargar_csv(REPO / "seed" / "transactions.csv")
    cfdis = [cx.parsear_archivo(p, "company_001", "CNM160812AB1",
                                base=REPO / "seed" / "cfdis")
             for p in sorted((REPO / "seed" / "cfdis").rglob("*.xml"))]
    s = profile_repo.sugerir_perfil(txns, cfdis)
    assert s["giro"] == "Servicios industriales / mantenimiento"
    assert (s["ciudad"], s["estado"], s["cp"]) == ("Querétaro", "Querétaro", "76087")
    assert s["tamanio"] == "pequeña"
    assert s["modelo"] == "mixto"


def test_upsert_valida_sin_db():
    # validación ocurre antes de tocar Supabase: sb=None nunca se usa
    with pytest.raises(ValueError, match="giro y ciudad"):
        profile_repo.upsert_profile(None, "company_001", {"giro": "", "ciudad": "X"})
    with pytest.raises(ValueError, match="modelo"):
        profile_repo.upsert_profile(None, "company_001",
                                    {"giro": "G", "ciudad": "C", "modelo": "otro"})


def test_consultant_incluye_perfil(monkeypatch):
    import app.agents.consultant as C

    visto = {}

    class FakeLLM:
        def run_tool_loop(self, system, history, tools, executor, model=None,
                          max_steps=8, **kwargs):
            visto["system"] = system
            return "ok", [], False

    monkeypatch.setattr(C.llm, "run_tool_loop", FakeLLM().run_tool_loop)
    C.ask("hola", perfil={"giro": "Panadería", "ciudad": "Querétaro",
                          "estado": "Querétaro", "tamanio": "micro",
                          "modelo": "b2c", "empleados": 5, "notas": ""})
    assert "Panadería" in visto["system"] and "Querétaro" in visto["system"]
    assert "PROHIBIDO inventar" in visto["system"]
    C.ask("hola")
    # sin perfil no hay bloque de contexto (segundo llamado pisa visto)
    assert "Contexto del negocio" not in visto["system"]


def test_endpoints_perfil(monkeypatch):
    client = TestClient(main.app)
    monkeypatch.setattr(main, "get_supabase", lambda: object())

    class SB:
        def table(self, name):
            parent = self

            class T:
                def select(self, *a, **k):
                    return self

                def eq(self, *a, **k):
                    return self

                def upsert(self, row, **k):
                    parent.saved = row
                    return self

                def execute(self):
                    return type("R", (), {"data": []})()
            return T()

    sb = SB()
    monkeypatch.setattr("app.repositories.profile_repo.get_profile",
                        lambda sb_, cid: None)
    # sugerencia desde XMLs del seed (hermético, sin DB)
    from app.integrations.sat import cfdi_xml as _cx
    monkeypatch.setattr(
        main, "_cfdis",
        lambda: [_cx.parsear_archivo(p, "company_001", "CNM160812AB1", base=REPO / "seed" / "cfdis")
                 for p in sorted((REPO / "seed" / "cfdis").rglob("*.xml"))])
    s = client.get("/api/company/profile/sugerencia").json()
    assert s["ciudad"] == "Querétaro" and s["tamanio"] == "pequeña"
    # PUT inválido -> 400 sin tocar DB
    r = client.put("/api/company/profile", json={"giro": "", "ciudad": ""})
    assert r.status_code == 400
    # GET sin fila -> no configurado (get_profile real contra FakeSB vacío)
    monkeypatch.setattr("app.repositories.profile_repo.get_profile",
                        lambda sb_, cid: None)
    assert client.get("/api/company/profile").json() == {
        "configurado": False, "perfil": None}
