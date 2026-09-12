"""Cobranza T9: plantilla, envío parcial, guardas y endpoints (repos simulados)."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import app.main as main
from app.integrations.mail.provider import MailError
from app.operator import collections as op

REPO = Path(__file__).resolve().parents[3]


def rec(rid, cfdi_uuid, rfc, total="1000.00"):
    return {"id": rid, "company_id": "company_001", "cfdi_id": cfdi_uuid,
            "customer_name": "CLIENTE " + rfc[:3], "customer_rfc": rfc,
            "amount": total, "amount_paid": "0", "amount_pending": total,
            "issued_at": "2026-08-10T12:00:00-06:00",
            "due_date": "2026-09-09T12:00:00-06:00", "status": "open"}


def cfdi(uuid, folio="1012"):
    return {"uuid": uuid, "serie": "A", "folio": folio}


COMPANY = {"razon_social": "CAFE NORTENO SA DE CV",
           "nombre_comercial": "Café Norteño"}


def test_plantilla_con_datos_reales():
    d = op.prepare_draft(rec("ar_1", "u", "CVN190830M83", "18500.00"),
                         cfdi("UUID-12345678", "1012"),
                         {"email": "a@x.com"}, COMPANY)
    assert d["contact_status"] == "listo" and d["to"] == "a@x.com"
    assert "A-1012" in d["subject"]
    for parte in ("UUID-123", "18,500.00", "2026-08-10", "2026-09-09", "Café Norteño"):
        assert parte in d["body"], parte


def test_falta_email_y_validacion():
    d = op.prepare_draft(rec("ar_1", "u", "X"), cfdi("u"), None, COMPANY)
    assert (d["contact_status"], d["to"]) == ("falta_email", None)
    assert op.email_valido("a@b.com") and not op.email_valido("no-es-mail")


class FakeProvider:
    name = "fake"
    def __init__(self, falla_en=()):
        self.falla_en = set(falla_en)
        self.enviados = []

    def send_email(self, *, to, subject, body):
        if to in self.falla_en:
            raise MailError("smtp caído")
        self.enviados.append(to)
        return {"id": "fake-1", "to": to}


def test_lote_parcial_no_se_bloquea():
    drafts = [
        {"receivable_id": f"ar_{i}", "to": f"c{i}@x.com" if i < 3 else None,
         "subject": "s", "body": "b"}
        for i in range(5)]
    reg = []
    res = op.send_batch(drafts, FakeProvider(), lambda rid: False,
                        reg.append, force=False)
    estados = [r["status"] for r in res]
    assert estados == ["enviada"] * 3 + ["bloqueada_falta_email"] * 2
    assert len(reg) == 3  # bloqueadas no registran intento (nada que auditar)


def test_guarda_24h_y_force():
    d = [{"receivable_id": "ar_1", "to": "c@x.com", "subject": "s", "body": "b"}]
    reg = []
    r1 = op.send_batch(d, FakeProvider(), lambda rid: True, reg.append)
    assert r1[0]["status"] == "omitida_24h" and reg[0]["status"] == "omitida_24h"
    r2 = op.send_batch(d, FakeProvider(), lambda rid: True, lambda x: None, force=True)
    assert r2[0]["status"] == "enviada"


def test_fallo_no_aborta_lote():
    drafts = [{"receivable_id": "ar_1", "to": "ok@x.com", "subject": "s", "body": "b"},
              {"receivable_id": "ar_2", "to": "bad@x.com", "subject": "s", "body": "b"}]
    reg = []
    res = op.send_batch(drafts, FakeProvider(falla_en={"bad@x.com"}),
                        lambda rid: False, reg.append)
    assert [r["status"] for r in res] == ["enviada", "fallida"]


# ---------- endpoints con repos simulados ----------

UUIDS = ["11111111-1111-4111-8111-111111111111",
         "22222222-2222-4222-8222-222222222222",
         "33333333-3333-4333-8333-333333333333"]


class StubCol:
    def __init__(self):
        self.contacts = {"RFC000000AAA": {"customer_rfc": "RFC000000AAA",
                                          "customer_name": "A",
                                          "email": "tengo@x.com"}}
        self.actions = []
        self.recientes = set()

    def list_contacts(self, sb, company_id):
        return list(self.contacts.values())

    def upsert_contact(self, sb, company_id, rfc, email, name="", phone=""):
        from app.operator.collections import email_valido
        if not email_valido(email):
            raise ValueError(f"email inválido: {email!r}")
        self.contacts[rfc.upper()] = {"customer_rfc": rfc.upper(),
                                      "customer_name": name, "email": email}
        return self.contacts[rfc.upper()]

    def enviado_reciente(self, sb, company_id, rid, horas=24):
        return rid in self.recientes

    def record_action(self, sb, company_id, item):
        self.actions.append(item)


def recs_stub():
    return [rec("ar_t1", UUIDS[0], "RFC000000AAA", "100.00"),
            rec("ar_t2", UUIDS[1], "RFC000000BBB", "200.00"),
            rec("ar_t3", UUIDS[2], "RFC000000CCC", "300.00")]


@pytest.fixture
def api(monkeypatch):
    from app.repositories.collections_repo import resolve as _resolve

    stub = StubCol()
    stub.resolve = staticmethod(_resolve)
    monkeypatch.setattr(main, "get_supabase", lambda: object())
    monkeypatch.setattr(main, "col", stub)
    monkeypatch.setattr(main.fr, "fetch_receivables", lambda sb, cid: recs_stub())
    # _cfdis real filtrado a nuestros UUIDs de prueba
    return stub, TestClient(main.app)


def _cfdi_objs():
    from app.schemas.cfdi import Cfdi
    from datetime import datetime
    return [Cfdi(uuid=u, company_id="company_001", tipo="emitido",
                 emisor_rfc="CNM160812AB1", emisor_nombre="CAFE",
                 receptor_rfc="R", receptor_nombre="R", total="1",
                 subtotal="1", iva="0",
                 fecha_emision=datetime(2026, 8, 1), concepto="X")
            for u in UUIDS]


def test_endpoints_draft_contacts_send(api, monkeypatch):
    stub, client = api
    monkeypatch.setattr(main, "_cfdis", lambda: _cfdi_objs())
    # draft: 1 listo + 2 falta_email
    d = client.get("/api/collections/draft").json()["items"]
    assert [(x["receivable_id"], x["contact_status"]) for x in d] == [
        ("ar_t1", "listo"), ("ar_t2", "falta_email"), ("ar_t3", "falta_email")]
    # cobertura del directorio
    cob = client.get("/api/collections/contacts").json()
    assert [c["tiene_email"] for c in cob["cobertura"]] == [True, False, False]
    # email inválido se rechaza
    assert client.post("/api/collections/contacts",
                       json={"customer_rfc": "RFC000000BBB",
                             "email": "mal"}).status_code == 400
    # sin confirm no envía nada
    r = client.post("/api/collections/send", json={})
    assert r.status_code == 400 and len(r.json()["detail"]["drafts"]) == 3
    # envío parcial: 1 de 3 (las otras ni se intentan)
    monkeypatch.setattr(main, "get_mail_provider",
                        lambda: FakeProvider())
    r = client.post("/api/collections/send",
                    json={"receivable_ids": ["ar_t1"], "confirm": True}).json()
    assert r["resumen"] == {"enviada": 1, "bloqueada_falta_email": 0,
                            "omitida_24h": 0, "fallida": 0}
    # envío total: 1 enviada + 2 bloqueadas (no frena el lote)
    r = client.post("/api/collections/send", json={"confirm": True}).json()
    assert r["resumen"]["enviada"] == 1
    assert r["resumen"]["bloqueada_falta_email"] == 2
    # alta manual habilita y reintento envía
    client.post("/api/collections/contacts",
                json={"customer_rfc": "RFC000000BBB", "email": "b@x.com"})
    r = client.post("/api/collections/send",
                    json={"receivable_ids": ["ar_t2"], "confirm": True}).json()
    assert r["resumen"]["enviada"] == 1


class _Q:
    def __init__(self, fn):
        self.fn = fn

    def execute(self):
        return self.fn()


class FakeSB:
    def __init__(self, previo):
        self.previo = previo
        self.upserted = None

    def table(self, name):
        parent = self

        class T:
            def select(self, *a, **k):
                return self

            def eq(self, *a, **k):
                return self

            def upsert(self, row, **k):
                parent.upserted = row
                return self

            def execute(self):
                return type("R", (), {"data": [parent.previo] if parent.previo else []})()
        return T()


def test_upsert_conserva_nombre_previo():
    from app.repositories import collections_repo as repo
    sb = FakeSB({"customer_rfc": "X", "customer_name": "NOMBRE VIEJO",
                 "email": None})
    repo.upsert_contact(sb, "company_001", "x", "nuevo@x.com")
    assert sb.upserted["email"] == "nuevo@x.com"
    assert sb.upserted["customer_name"] == "NOMBRE VIEJO"
    assert sb.upserted["customer_rfc"] == "X"


def test_resolve_por_nombre_con_rfc_compartido():
    from app.repositories.collections_repo import resolve
    contactos = [
        {"customer_rfc": "XAXX010101000", "customer_name": "A", "email": "a@x.com"},
        {"customer_rfc": "XAXX010101000", "customer_name": "B", "email": None},
        {"customer_rfc": "U", "customer_name": "C", "email": "c@x.com"},
    ]
    assert resolve(contactos, "XAXX010101000", "B")["customer_name"] == "B"
    assert resolve(contactos, "XAXX010101000", "") is None  # ambiguo sin nombre
    assert resolve(contactos, "U", "")["email"] == "c@x.com"
    assert resolve(contactos, "ZZZ", "") is None
