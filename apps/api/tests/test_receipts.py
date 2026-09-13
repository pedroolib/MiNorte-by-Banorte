"""Tickets (TIER 2): extracción, match reutilizando reconcile.py, payload
sin datos inventados, endpoints con repos simulados y el loop real del
Browser Agent contra una página local (sin red, sin LLM: `_decide` se
sustituye por un guión fijo — el flujo real contra un portal en vivo se
valida a mano, spec #19 prohíbe portales mock en el flujo principal)."""

from __future__ import annotations

import asyncio
from datetime import datetime
from decimal import Decimal
from urllib.parse import quote
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient

import app.main as main
from app.browser import actions as bactions
from app.browser import agent as bagent
from app.operator import receipts as op
from app.schemas.transaction import Transaction

MX = ZoneInfo("America/Mexico_City")


def T(id, fecha, monto, merchant="ALSUPER TOREO"):
    return Transaction(
        id=id, company_id="company_001", account_id="acc",
        amount=Decimal(monto), currency="MXN",
        date=datetime(2026, 9, fecha, 10, tzinfo=MX),
        description=f"MOV {id}", merchant_name=merchant, merchant_rfc=None,
        type="egreso", source="banorte_mock", categoria="tarjeta",
    )


# ---------- match_candidates reutiliza reconcile.py tal cual ----------

def test_match_candidates_reutiliza_formula_de_reconcile():
    extraction = {"comercio": "ALSUPER TOREO", "total": "163.00",
                  "fecha": "2026-09-06T09:59:00-06:00"}
    txns = [T("t1", 6, "163.00"), T("t2", 6, "50.00", merchant="OTRO COMERCIO")]
    out = op.match_candidates(extraction, txns)
    assert out[0]["transaction_id"] == "t1"
    assert out[0]["amount_score"] == Decimal("1")
    assert out[0]["merchant_score"] == Decimal("1")
    # ingresos nunca son candidatos (un ticket siempre es un gasto propio)
    ingreso = Transaction(**{**T("t3", 6, "163.00").model_dump(), "type": "ingreso"})
    assert all(c["transaction_id"] != "t3" for c in op.match_candidates(extraction, [ingreso]))


def test_match_candidates_sin_total_no_inventa_score():
    out = op.match_candidates({"comercio": "X"}, [T("t1", 6, "100.00", merchant="X")])
    assert out[0]["amount_score"] == Decimal("0")


# ---------- build_invoice_payload nunca inventa datos ----------

def test_build_invoice_payload_no_inventa_campos_faltantes():
    extraction = {"comercio": "ALSUPER TOREO", "rfc_comercio": None,
                  "total": "163.00", "fecha": "2026-09-06T09:59:00-06:00",
                  "folio": "0022936"}
    perfil = {"rfc": "CNM160812AB1", "razon_social": "CAFE NORTENO SA DE CV",
             "regimen_fiscal": "601", "email": "contacto@cafenorteno.mx"}
    payload = op.build_invoice_payload(extraction, perfil)
    assert payload["rfc_comercio"] is None  # Vision no lo leyó: sigue null
    assert payload["rfc_receptor"] == "CNM160812AB1"
    assert payload["folio_ticket"] == "0022936"
    assert payload["uso_cfdi"] == "G03"


def test_get_fiscal_profile_lee_seed_company_json():
    perfil = op.get_fiscal_profile()
    assert perfil["rfc"] and perfil["razon_social"]


# ---------- browser/actions: heurística de irreversibilidad ----------

def test_is_irreversible_por_keyword_y_por_type_submit():
    elements = [{"ref": "0", "label": "Solicitar factura", "type": ""},
               {"ref": "1", "label": "Siguiente", "type": ""},
               {"ref": "2", "label": "", "type": "submit"}]
    assert bactions.is_irreversible({"action": "click", "ref": "0"}, elements)
    assert not bactions.is_irreversible({"action": "click", "ref": "1"}, elements)
    assert bactions.is_irreversible({"action": "click", "ref": "2"}, elements)
    assert not bactions.is_irreversible({"action": "fill", "ref": "0"}, elements)
    # ref desconocido: seguro por defecto (spec: nunca autoconfirmar)
    assert bactions.is_irreversible({"action": "click", "ref": "99"}, elements)


# ---------- Browser Agent: loop real de Playwright, guion fijo ----------

FORM_HTML = """
<html><body>
  <input aria-label="RFC" placeholder="RFC" id="rfc">
  <button id="enviar" type="submit">Enviar factura</button>
</body></html>
"""
FORM_URL = "data:text/html," + quote(FORM_HTML)

# Un widget REAL (div.g-recaptcha visible), no solo la palabra "captcha"
# en el texto -- así se prueba el detector nuevo, no el viejo (regex
# sobre HTML crudo, que confundía el badge invisible de reCAPTCHA v3
# -presente en medio internet- con un freno real).
CAPTCHA_HTML = ('<html><body><div class="g-recaptcha" '
               'style="width:300px;height:76px">verificación</div></body></html>')
CAPTCHA_URL = "data:text/html," + quote(CAPTCHA_HTML)

# Patrón real de Wansoft: <label for=> aparte, el <input> no trae
# aria-label ni placeholder. Sin leer el <label>, dos campos vecinos
# (Correo/CP) llegan al modelo indistinguibles (label="" para ambos) y
# se pueden cruzar -- justo el bug real encontrado en vivo.
LABELED_FORM_HTML = """
<html><body>
  <label for="email">Correo electrónico</label>
  <input id="email" type="text">
  <label for="cp">CP</label>
  <input id="cp" type="text">
</body></html>
"""
LABELED_FORM_URL = "data:text/html;charset=utf-8," + quote(LABELED_FORM_HTML)


def test_snapshot_lee_label_for_no_solo_aria_label_o_placeholder():
    """Regresión del bug real: dos <input> sin aria-label/placeholder,
    con su texto en un <label for=> aparte, deben distinguirse por label
    (antes ambos llegaban con label="" y el modelo los podía cruzar)."""
    async def run():
        from playwright.async_api import async_playwright
        pw = await async_playwright().start()
        browser = await pw.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage"])
        page = await browser.new_page()
        await page.goto(LABELED_FORM_URL, wait_until="domcontentloaded")
        els = await bagent._snapshot(page)
        await browser.close()
        await pw.stop()
        return els

    els = asyncio.run(run())
    labels = {e["label"] for e in els}
    assert "Correo electrónico" in labels
    assert "CP" in labels


# Patrón real de Wansoft: el portal prellena "Código de factura" solo,
# desde el propio QR/URL del ticket -- sobreescribirlo con nuestro folio
# rompe el lookup real ("el ticket no existe"). El agente necesita VER
# ese valor para saber que no debe tocarlo.
PREFILLED_FORM_HTML = """
<html><body>
  <label for="codigo">Código de factura</label>
  <input id="codigo" type="text" value="260908045579019028">
  <label for="rfc">RFC</label>
  <input id="rfc" type="text" value="">
</body></html>
"""
PREFILLED_FORM_URL = "data:text/html;charset=utf-8," + quote(PREFILLED_FORM_HTML)


def test_snapshot_expone_el_valor_prellenado_por_el_portal():
    """Regresión del bug real: el agente sobreescribía 'Código de
    factura' (armado por el portal desde el QR) con el folio del ticket,
    rompiendo el lookup real ('el ticket no existe'). Sin ver el `value`
    actual no hay forma de que el agente sepa que ya está lleno."""
    async def run():
        from playwright.async_api import async_playwright
        pw = await async_playwright().start()
        browser = await pw.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage"])
        page = await browser.new_page()
        await page.goto(PREFILLED_FORM_URL, wait_until="domcontentloaded")
        els = await bagent._snapshot(page)
        await browser.close()
        await pw.stop()
        return els

    els = asyncio.run(run())
    codigo = next(e for e in els if e["label"] == "Código de factura")
    rfc = next(e for e in els if e["label"] == "RFC")
    assert codigo["value"] == "260908045579019028"
    assert rfc["value"] == ""


# Patrón real: tras EMITIR FACTURA aparece un modal de éxito encima del
# formulario viejo. Sin filtrar lo tapado, el agente seguía viendo
# "EMITIR FACTURA" y lo intentaba dar otra vez en vez de solo ver
# "Aceptar" (así se coló el reintento accidental de envío).
MODAL_FORM_HTML = """
<html><body>
  <button id="old" style="position:absolute; top:300px; left:300px;
    width:150px; height:40px;">EMITIR FACTURA</button>
  <div id="overlay" style="position:fixed; inset:0; background:rgba(0,0,0,.5); z-index:1000;">
    <button id="aceptar" style="position:absolute; top:20px; left:20px;
      width:100px; height:30px;">Aceptar</button>
  </div>
</body></html>
"""
MODAL_FORM_URL = "data:text/html;charset=utf-8," + quote(MODAL_FORM_HTML)


def test_snapshot_excluye_elementos_tapados_por_un_modal():
    async def run():
        from playwright.async_api import async_playwright
        pw = await async_playwright().start()
        browser = await pw.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage"])
        page = await browser.new_page()
        await page.goto(MODAL_FORM_URL, wait_until="domcontentloaded")
        els = await bagent._snapshot(page)
        await browser.close()
        await pw.stop()
        return els

    els = asyncio.run(run())
    labels = {e["label"] for e in els}
    assert "Aceptar" in labels
    assert "EMITIR FACTURA" not in labels  # tapado por el modal: no se ofrece


def test_browser_agent_se_detiene_antes_de_la_accion_irreversible(monkeypatch):
    """El agente llena el RFC real y se detiene ANTES de dar 'Enviar
    factura' (spec #19: confirmación humana antes de lo irreversible)."""
    script = iter([
        {"action": "fill", "ref": None, "value": None, "source_field": None,
         "missing_field": None, "reason": "llenar rfc"},
        {"action": "click", "ref": None, "value": None, "source_field": None,
         "missing_field": None, "reason": "enviar"},
    ])

    FINISH = {"action": "finish", "ref": None, "value": None, "source_field": None,
             "missing_field": None, "reason": "listo"}

    def fake_decide(url, title, elements, invoice_data, history, model=None):
        step = next(script, FINISH)
        if step["action"] == "fill":
            ref = next(e["ref"] for e in elements if "rfc" in (e["label"] or "").lower())
            return {**step, "ref": ref, "value": invoice_data["rfc_receptor"],
                    "source_field": "rfc_receptor"}
        if step["action"] == "click":
            ref = next(e["ref"] for e in elements if e.get("type") == "submit")
            return {**step, "ref": ref}
        return step

    monkeypatch.setattr(bagent, "_decide", fake_decide)

    # Una sola sesión de asyncio: Playwright no tolera que start/confirm/close
    # corran en loops distintos (cada asyncio.run crea uno nuevo).
    async def run():
        sess = await bagent.start(
            "test-session-1", FORM_URL,
            {"rfc_receptor": "CNM160812AB1"}, headless=True)
        assert sess.status == "esperando_confirmacion"
        assert sess.pending_action["action"] == "click"
        assert len(sess.steps) == 1 and "fill" in sess.steps[0]["result"]

        confirmed = await bagent.confirm("test-session-1", approve=True)
        await bagent.close("test-session-1")
        return confirmed

    confirmed = asyncio.run(run())
    assert confirmed.steps[-1]["confirmado_por_humano"] is True
    assert confirmed.status == "resuelta"


def test_browser_agent_rechazo_cancela_sesion(monkeypatch):
    def fake_decide(url, title, elements, invoice_data, history, model=None):
        ref = next(e["ref"] for e in elements if e.get("type") == "submit")
        return {"action": "click", "ref": ref, "value": None,
               "missing_field": None, "reason": "enviar"}

    monkeypatch.setattr(bagent, "_decide", fake_decide)

    async def run():
        sess = await bagent.start("test-session-2", FORM_URL,
                                  {}, headless=True)
        assert sess.status == "esperando_confirmacion"
        return await bagent.confirm("test-session-2", approve=False)

    rechazada = asyncio.run(run())
    assert rechazada.status == "cancelada"
    assert bagent.get("test-session-2") is None


def test_browser_agent_download_captura_el_xml_real(monkeypatch):
    """action=download debe capturar el CONTENIDO real del archivo (no
    solo confirmar visualmente que 'se emitió'): así se puede conciliar
    de verdad en vez de depender de que alguien pegue el XML a mano."""
    import base64

    xml_bytes = b"<?xml version='1.0'?><cfdi:Comprobante>fake-cfdi</cfdi:Comprobante>"
    b64 = base64.b64encode(xml_bytes).decode()
    html = (
        "<html><body>"
        f'<a download="factura.xml" href="data:text/xml;base64,{b64}">Descargar XML</a>'
        "</body></html>"
    )
    url = "data:text/html," + quote(html)

    FINISH = {"action": "finish", "ref": None, "value": None,
             "missing_field": None, "reason": "listo"}
    asked = iter([{"action": "download", "ref": None, "value": None,
                   "missing_field": None, "reason": "bajar el xml del cfdi"}])

    def fake_decide(u, t, elements, invoice_data, history, model=None):
        step = next(asked, None)
        if step is None:
            return FINISH
        ref = next(e["ref"] for e in elements if "descargar" in (e["label"] or "").lower())
        return {**step, "ref": ref}

    monkeypatch.setattr(bagent, "_decide", fake_decide)

    async def run():
        sess = await bagent.start("test-session-8", url, {}, headless=True)
        await bagent.close("test-session-8")
        return sess

    sess = asyncio.run(run())
    assert sess.status == "resuelta"
    assert sess.downloaded_xml is not None
    assert "cfdi:Comprobante" in sess.downloaded_xml


def test_browser_agent_provide_input_resume(monkeypatch):
    """spec #19 `request_user_input`: un humano da el dato faltante y el
    agente sigue navegando desde donde se quedó (no reinicia)."""
    FINISH = {"action": "finish", "ref": None, "value": None,
             "missing_field": None, "reason": "listo"}
    asked = iter([{"action": "request_user_input", "ref": None, "value": None,
                   "missing_field": "cp_receptor", "reason": "el portal pide CP"}])

    def fake_decide(url, title, elements, invoice_data, history, model=None):
        step = next(asked, None)
        if step is not None:
            return step
        assert invoice_data.get("cp_receptor") == "76000"
        return FINISH

    monkeypatch.setattr(bagent, "_decide", fake_decide)

    async def run():
        sess = await bagent.start("test-session-3", FORM_URL, {}, headless=True)
        assert sess.status == "bloqueada_datos_faltantes"
        assert sess.pending_action["missing_field"] == "cp_receptor"
        resumed = await bagent.provide_input("test-session-3", "cp_receptor", "76000")
        await bagent.close("test-session-3")
        return resumed

    resumed = asyncio.run(run())
    assert resumed.invoice_data["cp_receptor"] == "76000"
    assert resumed.status == "resuelta"


def test_browser_agent_rechaza_fill_con_valor_no_respaldado(monkeypatch):
    """Regresión del bug real: el modelo intentó llenar 'CP' con el valor
    de razón social ('PUBLICO EN GENERAL', truncado a 'PUBLI' por el
    maxlength real del campo) en vez de pedir el dato porque cp_receptor
    no estaba en invoice_data. El servidor debe rechazarlo (nunca confiar
    solo en que el prompt baste) y tratarlo como dato faltante, sin
    escribir nada — invoice_data['cp_receptor'] no existe, así que
    cualquier `value` para ese source_field es, por definición, falso."""
    def fake_decide(url, title, elements, invoice_data, history, model=None):
        ref = next(e["ref"] for e in elements if "rfc" in (e["label"] or "").lower())
        return {"action": "fill", "ref": ref,
               "value": invoice_data["razon_social_receptor"],  # dato de OTRO campo
               "source_field": "cp_receptor",  # dice ser el CP, pero no lo es
               "missing_field": None, "reason": "relleno equivocado"}

    monkeypatch.setattr(bagent, "_decide", fake_decide)

    async def run():
        sess = await bagent.start(
            "test-session-9", FORM_URL,
            {"razon_social_receptor": "PUBLICO EN GENERAL"}, headless=True)
        await bagent.close("test-session-9")
        return sess

    sess = asyncio.run(run())
    assert sess.status == "bloqueada_datos_faltantes"
    assert len(sess.steps) == 0  # nunca se ejecutó el fill


def test_browser_agent_rechaza_source_field_ausente(monkeypatch):
    def fake_decide(url, title, elements, invoice_data, history, model=None):
        ref = next(e["ref"] for e in elements if "rfc" in (e["label"] or "").lower())
        return {"action": "fill", "ref": ref, "value": invoice_data["rfc_receptor"],
               "source_field": None, "missing_field": None, "reason": "sin fuente"}

    monkeypatch.setattr(bagent, "_decide", fake_decide)

    async def run():
        sess = await bagent.start("test-session-10", FORM_URL,
                                  {"rfc_receptor": "CNM160812AB1"}, headless=True)
        await bagent.close("test-session-10")
        return sess

    sess = asyncio.run(run())
    assert sess.status == "bloqueada_datos_faltantes"
    assert len(sess.steps) == 0


def test_browser_agent_provide_input_sin_sesion_pendiente(monkeypatch):
    from app.browser.agent import BrowserAgentError

    async def run():
        with pytest.raises(BrowserAgentError):
            await bagent.provide_input("no-existe", "cp_receptor", "76000")

    asyncio.run(run())


def test_browser_agent_resume_tras_captcha_resuelto_a_mano(monkeypatch):
    """Human-in-the-loop: el CAPTCHA se resuelve en la ventana visible
    (headless=False); `resume()` sigue navegando desde ahí, no reinicia."""
    FINISH = {"action": "finish", "ref": None, "value": None,
             "missing_field": None, "reason": "listo"}
    monkeypatch.setattr(bagent, "_decide", lambda *a, **k: FINISH)

    async def run():
        sess = await bagent.start("test-session-5", CAPTCHA_URL, {}, headless=True)
        assert sess.status == "bloqueada_captcha"
        # simula al humano resolviendo el captcha en la ventana real
        await sess.page.set_content("<html><body>ok</body></html>")
        resumed = await bagent.resume("test-session-5")
        await bagent.close("test-session-5")
        return resumed

    resumed = asyncio.run(run())
    assert resumed.status == "resuelta"


def test_browser_agent_resume_rechaza_status_no_resumible(monkeypatch):
    from app.browser.agent import BrowserAgentError

    def fake_decide(url, title, elements, invoice_data, history, model=None):
        ref = next(e["ref"] for e in elements if e.get("type") == "submit")
        return {"action": "click", "ref": ref, "value": None,
               "missing_field": None, "reason": "enviar"}

    monkeypatch.setattr(bagent, "_decide", fake_decide)

    async def run():
        sess = await bagent.start("test-session-6", FORM_URL, {}, headless=True)
        assert sess.status == "esperando_confirmacion"  # no es resumable
        with pytest.raises(BrowserAgentError):
            await bagent.resume("test-session-6")
        await bagent.close("test-session-6")

    asyncio.run(run())


def test_browser_agent_screenshot_funciona_headless(monkeypatch):
    """Verificación visual sin ventana visible (útil para revisar qué
    pasó de verdad tras una corrida oculta, spec #5)."""
    monkeypatch.setattr(bagent, "_decide", lambda *a, **k: {
        "action": "finish", "ref": None, "value": None,
        "missing_field": None, "reason": "listo"})

    async def run():
        sess = await bagent.start("test-session-7", FORM_URL, {}, headless=True)
        assert sess.status == "resuelta"
        png = await bagent.screenshot("test-session-7")
        await bagent.close("test-session-7")
        return png

    png = asyncio.run(run())
    assert png[:8] == b"\x89PNG\r\n\x1a\n"  # firma PNG real, no basura


def test_browser_agent_screenshot_sin_sesion(monkeypatch):
    from app.browser.agent import BrowserAgentError

    async def run():
        with pytest.raises(BrowserAgentError):
            await bagent.screenshot("no-existe")

    asyncio.run(run())


# ---------- endpoints con repos simulados (mismo patrón que cobranza) ----------

class StubReceipts:
    def __init__(self):
        self.docs: dict[str, dict] = {}
        self.tickets: dict[str, dict] = {}
        self._n = 0

    def _id(self):
        self._n += 1
        return f"id_{self._n}"

    def create_document(self, sb, company_id, mime, extraction, storage_path=None, kind="receipt"):
        doc = {"id": self._id(), "company_id": company_id, "mime": mime,
               "extraction": extraction, "storage_path": storage_path, "kind": kind}
        self.docs[doc["id"]] = doc
        return doc

    def get_document(self, sb, company_id, document_id):
        return self.docs.get(document_id)

    def create_invoice_request(self, sb, company_id, document_id, transaction_id, payload, status="borrador"):
        row = {"id": self._id(), "company_id": company_id, "document_id": document_id,
               "transaction_id": transaction_id, "payload": payload, "status": status, "steps": []}
        self.tickets[row["id"]] = row
        return row

    def get_invoice_request(self, sb, company_id, invoice_id):
        return self.tickets.get(invoice_id)

    def list_invoice_requests(self, sb, company_id):
        return list(self.tickets.values())

    def update_invoice_request(self, sb, company_id, invoice_id, fields):
        self.tickets[invoice_id].update(fields)
        return self.tickets[invoice_id]


@pytest.fixture
def client(monkeypatch):
    import app.routes.tickets as routes

    stub = StubReceipts()
    monkeypatch.setattr(routes, "get_supabase", lambda: object())
    monkeypatch.setattr("app.repositories.receipts_repo.create_document", stub.create_document)
    monkeypatch.setattr("app.repositories.receipts_repo.get_document", stub.get_document)
    monkeypatch.setattr("app.repositories.receipts_repo.create_invoice_request", stub.create_invoice_request)
    monkeypatch.setattr("app.repositories.receipts_repo.get_invoice_request", stub.get_invoice_request)
    monkeypatch.setattr("app.repositories.receipts_repo.list_invoice_requests", stub.list_invoice_requests)
    monkeypatch.setattr("app.repositories.receipts_repo.update_invoice_request", stub.update_invoice_request)
    return stub, TestClient(main.app)


def test_upload_extrae_y_propone_candidatos(client, monkeypatch):
    _, c = client
    monkeypatch.setattr(
        "app.integrations.invoicing.vision.extract_receipt",
        lambda image_bytes, mime: {"comercio": "ALSUPER TOREO", "rfc_comercio": None,
                                   "total": "163.00", "fecha": "2026-09-06T09:59:00-06:00",
                                   "folio": "0022936", "confianza": "alta",
                                   "campos_no_legibles": []})
    r = c.post("/api/tickets/upload",
              files={"file": ("ticket.jpg", b"fake-bytes", "image/jpeg")})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["document"]["extraction"]["comercio"] == "ALSUPER TOREO"
    assert "candidates" in body


def test_upload_rechaza_archivo_vacio(client):
    _, c = client
    r = c.post("/api/tickets/upload",
              files={"file": ("ticket.jpg", b"", "image/jpeg")})
    assert r.status_code == 400


def test_crear_ticket_y_listar(client):
    stub, c = client
    doc = stub.create_document(None, "company_001", "image/jpeg",
                               {"comercio": "X", "total": "10.00"})
    r = c.post("/api/tickets", json={"document_id": doc["id"], "transaction_id": "t1"})
    assert r.status_code == 200, r.text
    ticket = r.json()
    assert ticket["status"] == "listo_para_portal"
    assert ticket["payload"]["rfc_receptor"]

    r = c.get("/api/tickets")
    assert len(r.json()["items"]) == 1
    r = c.get(f"/api/tickets/{ticket['id']}")
    assert r.status_code == 200


def test_crear_ticket_sin_match_tambien_queda_listo(client):
    """Un ticket sin movimiento bancario conocido (efectivo, tarjeta
    personal...) se factura igual: el match es para reconciliar después,
    no un requisito para poder facturar."""
    stub, c = client
    doc = stub.create_document(None, "company_001", "image/jpeg",
                               {"comercio": "X", "total": "10.00"})
    r = c.post("/api/tickets", json={"document_id": doc["id"], "transaction_id": None})
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "listo_para_portal"


def test_crear_ticket_receptor_generico_usa_publico_en_general(client):
    """Demo con portal real: la empresa ficticia del seed no existe en el
    SAT real (un portal lo rechaza); 'público en general' es el RFC real
    y universal que sí completa el flujo hasta un CFDI real."""
    stub, c = client
    doc = stub.create_document(None, "company_001", "image/jpeg",
                               {"comercio": "X", "total": "10.00"})
    r = c.post("/api/tickets", json={
        "document_id": doc["id"], "transaction_id": None,
        "receptor_generico": True,
    })
    assert r.status_code == 200, r.text
    payload = r.json()["payload"]
    assert payload["rfc_receptor"] == "XAXX010101000"
    assert payload["razon_social_receptor"] == "CLIENTE GENERICO"
    assert payload["regimen_fiscal_receptor"] == "616"
    assert payload["uso_cfdi"] == "S01"
    # el correo de entrega es independiente de la identidad fiscal: se
    # mantiene el real (seed/company.json), no se pierde ni se inventa
    assert payload["email_receptor"] == op.get_fiscal_profile()["email"]


def test_finalize_state_autoconcilia_al_descargar_xml(client, monkeypatch):
    """Cierre real del ciclo pedido para el demo: ticket -> agente -> XML
    descargado -> reconcile_cfdi -> cfdi_uuid persistido, sin que nadie
    tenga que copiar/pegar el XML a mano.

    `_finalize_state` es sync y se llama directo (no vía TestClient):
    Playwright no tolera cruzar el portal de event loop que usa
    starlette.TestClient para correr el endpoint async — probado aparte
    (test_browser_agent_download_captura_el_xml_real) que la descarga en
    sí funciona vía el loop real de la app (uvicorn), solo esta pieza de
    plomería se aísla aquí."""
    import base64

    import app.routes.tickets as routes_tickets

    stub, c = client
    doc = stub.create_document(None, "company_001", "image/jpeg", {"comercio": "Peckers"})
    ticket = stub.create_invoice_request(None, "company_001", doc["id"], "txn_1", {})

    xml_bytes = b"<?xml version='1.0'?><cfdi:Comprobante>fake-cfdi</cfdi:Comprobante>"
    b64 = base64.b64encode(xml_bytes).decode()
    html = ("<html><body>"
           f'<a download="factura.xml" href="data:text/xml;base64,{b64}">Descargar XML</a>'
           "</body></html>")
    url = "data:text/html," + quote(html)

    FINISH = {"action": "finish", "ref": None, "value": None,
             "missing_field": None, "reason": "listo"}
    asked = iter([{"action": "download", "ref": None, "value": None,
                   "missing_field": None, "reason": "bajar xml"}])

    def fake_decide(u, t, elements, invoice_data, history, model=None):
        step = next(asked, None)
        if step is None:
            return FINISH
        ref = next(e["ref"] for e in elements if "descargar" in (e["label"] or "").lower())
        return {**step, "ref": ref}

    monkeypatch.setattr(bagent, "_decide", fake_decide)
    monkeypatch.setattr(
        "app.operator.receipts.reconcile_cfdi",
        lambda sb, cid, txid, xml: {"status": "reconciled", "cfdi_uuid": "TEST-UUID-123"})

    async def run():
        sess = await bagent.start(ticket["id"], url, {}, headless=True)
        assert sess.status == "resuelta"
        assert sess.downloaded_xml is not None
        routes_tickets._finalize_state(object(), ticket["id"], sess.public_state())
        await bagent.close(ticket["id"])

    asyncio.run(run())
    saved = stub.get_invoice_request(None, "company_001", ticket["id"])
    assert saved["cfdi_uuid"] == "TEST-UUID-123"


def test_screenshot_endpoint_sin_sesion_viva(client):
    stub, c = client
    doc = stub.create_document(None, "company_001", "image/jpeg", {})
    ticket = stub.create_invoice_request(None, "company_001", doc["id"], None, {})
    r = c.get(f"/api/tickets/{ticket['id']}/screenshot")
    assert r.status_code == 409


def test_cancelar_ticket_sin_sesion_viva(client):
    stub, c = client
    doc = stub.create_document(None, "company_001", "image/jpeg", {})
    ticket = stub.create_invoice_request(None, "company_001", doc["id"], None, {})
    r = c.post(f"/api/tickets/{ticket['id']}/cancel")
    assert r.status_code == 200
    assert r.json()["status"] == "cancelada"


def test_provide_input_endpoint_validaciones(client):
    stub, c = client
    doc = stub.create_document(None, "company_001", "image/jpeg", {})
    ticket = stub.create_invoice_request(None, "company_001", doc["id"], None, {})
    r = c.post(f"/api/tickets/{ticket['id']}/provide_input", json={})
    assert r.status_code == 400
    r = c.post(f"/api/tickets/{ticket['id']}/provide_input",
              json={"field": "cp_receptor", "value": "76000"})
    assert r.status_code == 409  # sin sesión de browser viva


def test_resume_endpoint_sin_sesion_viva(client):
    stub, c = client
    doc = stub.create_document(None, "company_001", "image/jpeg", {})
    ticket = stub.create_invoice_request(None, "company_001", doc["id"], None, {})
    r = c.post(f"/api/tickets/{ticket['id']}/resume", json={})
    assert r.status_code == 409
