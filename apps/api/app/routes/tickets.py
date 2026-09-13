"""Tickets (spec #3.3 caso 1, #19, TIER 2): foto real -> factura real.

    POST /api/tickets/upload         foto -> extracción Vision + candidatos
    POST /api/tickets                crea invoice_request (match confirmado)
    GET  /api/tickets                lista (para la UI de /tickets)
    GET  /api/tickets/{id}           detalle + estado del browser agent
    POST /api/tickets/{id}/start     arranca el Browser Agent sobre el portal real
    POST /api/tickets/{id}/confirm   aprueba/rechaza la acción irreversible pendiente
    POST /api/tickets/{id}/cancel    cierra la sesión del navegador

No se tocan `financial/engine.py` ni `financial/reconcile.py`: los scores
de match se reutilizan tal cual desde `operator/receipts.py`.
"""

from __future__ import annotations

from contextlib import contextmanager

from fastapi import APIRouter, HTTPException, Response, UploadFile

from app.browser import agent as browser_agent
from app.config import get_settings
from app.db import get_supabase
from app.integrations.invoicing import vision
from app.operator import receipts as op

router = APIRouter(prefix="/api/tickets", tags=["tickets"])

MAX_UPLOAD_BYTES = 8 * 1024 * 1024  # 8MB: fotos de cámara reales, no XL


def _sb_or_503():
    sb = get_supabase()
    if sb is None:
        raise HTTPException(503, "sin Supabase: configura SUPABASE_URL/KEY en .env")
    return sb


@contextmanager
def _pg_errors():
    """Tabla `documents`/`invoice_requests` no existe todavía -> 503 con la
    instrucción (mismo patrón que el resto de la API), nunca un 500 plano."""
    try:
        yield
    except HTTPException:
        raise
    except Exception as e:
        msg = str(e)
        if "PGRST205" in msg or "PGRST204" in msg or "Could not find the table" in msg:
            raise HTTPException(503, f"corre migrations/013_tickets.sql ({e})")
        raise


def _company_id() -> str:
    return get_settings().COMPANY_ID


def _finalize_state(sb, ticket_id: str, state: dict, extra_fields: dict | None = None) -> None:
    """Persiste el estado del agente y, si terminó con un XML real
    descargado (`action=download`), concilia automáticamente: cierra el
    ciclo real ticket -> factura -> CFDI -> conciliación sin copiar/pegar,
    para que el resto del dashboard (alertas, sin_factura) lo refleje."""
    from app.repositories import receipts_repo

    fields = {"status": state["status"], "steps": state["steps"], **(extra_fields or {})}
    if state["status"] == "resuelta":
        live = browser_agent.get(ticket_id)
        if live is not None and live.downloaded_xml:
            with _pg_errors():
                row = receipts_repo.get_invoice_request(sb, _company_id(), ticket_id)
            result = op.reconcile_cfdi(
                sb, _company_id(), row.get("transaction_id") if row else None,
                live.downloaded_xml)
            if result.get("status") == "reconciled":
                fields["cfdi_uuid"] = result.get("cfdi_uuid")
    with _pg_errors():
        receipts_repo.update_invoice_request(sb, _company_id(), ticket_id, fields)


def _jd(v):
    """Decimal/datetime -> JSON-safe (mismo patrón que main.py)."""
    from datetime import datetime as _dt
    from decimal import Decimal as _D
    if isinstance(v, _D):
        return str(v)
    if isinstance(v, _dt):
        return v.isoformat()
    if isinstance(v, dict):
        return {k: _jd(x) for k, x in v.items()}
    if isinstance(v, list):
        return [_jd(x) for x in v]
    return v


@router.post("/upload")
async def upload_ticket(file: UploadFile):
    """Foto real del ticket -> extracción Vision + candidatos de match
    contra los egresos ya conocidos (misma fórmula que `reconcile.py`)."""
    from app.agents.llm import LLMError

    image_bytes = await file.read()
    if not image_bytes:
        raise HTTPException(400, "archivo vacío")
    if len(image_bytes) > MAX_UPLOAD_BYTES:
        raise HTTPException(400, f"foto muy grande (máx {MAX_UPLOAD_BYTES // (1024*1024)}MB)")

    try:
        extraction = vision.extract_receipt(image_bytes, file.content_type or "image/jpeg")
    except LLMError as e:
        raise HTTPException(502, f"modelo de visión no disponible: {e}")

    if not extraction.get("portal_facturacion"):
        # muchos tickets solo traen un QR (sin URL legible como texto);
        # decodificarlo es tan real como leer un dato impreso, no se inventa
        from app.integrations.invoicing import qr

        qr_url = qr.decode_url(image_bytes)
        if qr_url:
            extraction["portal_facturacion"] = qr_url
            no_legibles = extraction.get("campos_no_legibles") or []
            extraction["campos_no_legibles"] = [
                c for c in no_legibles if c != "portal_facturacion"]

    from app import data
    from app.repositories import receipts_repo

    candidates = op.match_candidates(extraction, data.get_transactions())
    sb = _sb_or_503()
    with _pg_errors():
        doc = receipts_repo.create_document(sb, _company_id(),
                                            file.content_type or "image/jpeg", extraction)
    return {"document": _jd(doc), "extraction": _jd(extraction),
            "candidates": _jd(candidates)}


@router.post("")
def create_invoice_request(body: dict):
    """Confirma el match elegido por el usuario y prepara el payload real
    para el Browser Agent (spec: nunca inventar datos)."""
    from app.repositories import receipts_repo

    sb = _sb_or_503()
    document_id = body.get("document_id")
    transaction_id = body.get("transaction_id")
    if not document_id:
        raise HTTPException(400, "document_id requerido")
    with _pg_errors():
        doc = receipts_repo.get_document(sb, _company_id(), document_id)
    if not doc:
        raise HTTPException(404, "documento no existe")
    if body.get("receptor_generico"):
        # SAT "público en general": RFC real y universalmente válido para
        # probar el flujo contra un portal real sin depender de que la
        # empresa ficticia del seed exista en el SAT (no existe). Solo
        # cambia la IDENTIDAD fiscal (rfc/razón social/régimen); el
        # correo de entrega es independiente de eso, así que si hay uno
        # real configurado se mantiene (si no, el agente lo pide él solo).
        perfil = dict(op.PUBLICO_EN_GENERAL)
        try:
            real_perfil = op.get_fiscal_profile()
            if real_perfil.get("email"):
                perfil["email"] = real_perfil["email"]
        except ValueError:
            pass
        uso_cfdi_default = op.USO_CFDI_PUBLICO_EN_GENERAL
    else:
        try:
            perfil = op.get_fiscal_profile()
        except ValueError as e:
            raise HTTPException(503, str(e))
        uso_cfdi_default = "G03"
    payload = op.build_invoice_payload(doc["extraction"], perfil,
                                       body.get("uso_cfdi", uso_cfdi_default))
    # listo_para_portal siempre: el match a un movimiento es para la
    # reconciliación posterior, no un requisito para poder facturar (un
    # ticket sin movimiento conocido -- efectivo, tarjeta personal, etc.
    # -- se factura igual, solo que reconcile_cfdi no tendrá qué conciliar).
    with _pg_errors():
        row = receipts_repo.create_invoice_request(
            sb, _company_id(), document_id, transaction_id, payload,
            status="listo_para_portal")
    return _jd(row)


@router.get("")
def list_tickets():
    from app.repositories import receipts_repo

    sb = _sb_or_503()
    with _pg_errors():
        items = receipts_repo.list_invoice_requests(sb, _company_id())
    return {"items": _jd(items)}


def _merge_live_session(row: dict) -> dict:
    """Si hay una sesión de browser viva para este ticket, su estado manda
    sobre lo último guardado (la sesión en memoria es la fuente de verdad
    mientras corre; se persiste al terminar)."""
    live = browser_agent.get(row["id"])
    if live is not None:
        state = live.public_state()
        row = {**row, "status": state["status"], "steps": state["steps"],
               "pending_action": state["pending_action"]}
    return row


@router.get("/{ticket_id}")
def get_ticket(ticket_id: str):
    from app.repositories import receipts_repo

    sb = _sb_or_503()
    with _pg_errors():
        row = receipts_repo.get_invoice_request(sb, _company_id(), ticket_id)
    if not row:
        raise HTTPException(404, "ticket no existe")
    return _jd(_merge_live_session(row))


@router.get("/{ticket_id}/screenshot")
async def screenshot_ticket(ticket_id: str):
    """Captura de la página real en este momento (sirve corriendo headless:
    no hace falta 'mostrar el navegador' para ver qué está pasando)."""
    from app.browser.agent import BrowserAgentError

    try:
        png = await browser_agent.screenshot(ticket_id)
    except BrowserAgentError as e:
        raise HTTPException(409, str(e))
    return Response(content=png, media_type="image/png")


@router.post("/{ticket_id}/start")
async def start_ticket(ticket_id: str, body: dict | None = None):
    """Arranca el Browser Agent sobre el portal REAL de facturación.

    body: {portal_url, headless?: bool}. Nunca navega portales mock
    (spec #19/#25): la URL la trae el usuario (el comercio real del ticket).
    """
    from app.repositories import receipts_repo

    body = body or {}
    portal_url = body.get("portal_url")
    if not portal_url:
        raise HTTPException(400, "portal_url requerido (el portal real de facturación del comercio)")

    sb = _sb_or_503()
    with _pg_errors():
        row = receipts_repo.get_invoice_request(sb, _company_id(), ticket_id)
    if not row:
        raise HTTPException(404, "ticket no existe")

    sess = await browser_agent.start(
        ticket_id, portal_url, row["payload"],
        headless=bool(body.get("headless", True)))
    state = sess.public_state()
    _finalize_state(sb, ticket_id, state)
    return _jd(state)


@router.post("/{ticket_id}/confirm")
async def confirm_ticket(ticket_id: str, body: dict):
    """Aprueba o rechaza la acción irreversible pendiente (spec: nunca se
    autoconfirma). body: {approve: bool}."""
    from app.browser.agent import BrowserAgentError

    sb = _sb_or_503()
    try:
        sess = await browser_agent.confirm(ticket_id, bool(body.get("approve")))
    except BrowserAgentError as e:
        raise HTTPException(409, str(e))
    state = sess.public_state()
    _finalize_state(sb, ticket_id, state)
    return _jd(state)


@router.post("/{ticket_id}/provide_input")
async def provide_input_ticket(ticket_id: str, body: dict):
    """Rellena un dato que Vision no pudo leer (spec #19: `request_user_input`)
    y reanuda el agente. body: {field: str, value: str}."""
    from app.browser.agent import BrowserAgentError
    from app.repositories import receipts_repo

    field = (body or {}).get("field")
    value = (body or {}).get("value")
    if not field or value is None or not str(value).strip():
        raise HTTPException(400, "field y value requeridos")

    sb = _sb_or_503()
    with _pg_errors():
        row = receipts_repo.get_invoice_request(sb, _company_id(), ticket_id)
    if not row:
        raise HTTPException(404, "ticket no existe")

    try:
        sess = await browser_agent.provide_input(ticket_id, field, str(value))
    except BrowserAgentError as e:
        raise HTTPException(409, str(e))
    state = sess.public_state()
    _finalize_state(sb, ticket_id, state, {"payload": {**row["payload"], field: value}})
    return _jd(state)


@router.post("/{ticket_id}/resume")
async def resume_ticket(ticket_id: str, body: dict | None = None):
    """Reanuda tras CAPTCHA resuelto a mano (ventana visible, headless=False)
    o para seguir más allá del límite de pasos. body: {extra_steps?: int}."""
    from app.browser.agent import BrowserAgentError

    sb = _sb_or_503()
    try:
        sess = await browser_agent.resume(ticket_id, extra_steps=int((body or {}).get("extra_steps") or 0))
    except BrowserAgentError as e:
        raise HTTPException(409, str(e))
    state = sess.public_state()
    _finalize_state(sb, ticket_id, state)
    return _jd(state)


@router.post("/{ticket_id}/cancel")
async def cancel_ticket(ticket_id: str):
    from app.repositories import receipts_repo

    sb = _sb_or_503()
    await browser_agent.close(ticket_id)
    with _pg_errors():
        row = receipts_repo.update_invoice_request(sb, _company_id(), ticket_id,
                                                   {"status": "cancelada"})
    return _jd(row)


@router.post("/{ticket_id}/reconcile")
def reconcile_ticket(ticket_id: str, body: dict | None = None):
    """CFDI real obtenido del portal -> reconciliación real (último paso,
    spec #3.3 caso 1). body: {cfdi_xml?: str} si el portal entregó XML."""
    from app.repositories import receipts_repo

    sb = _sb_or_503()
    with _pg_errors():
        row = receipts_repo.get_invoice_request(sb, _company_id(), ticket_id)
    if not row:
        raise HTTPException(404, "ticket no existe")
    result = op.reconcile_cfdi(sb, _company_id(), row.get("transaction_id"),
                               (body or {}).get("cfdi_xml"))
    with _pg_errors():
        updated = receipts_repo.update_invoice_request(sb, _company_id(), ticket_id, {
            "status": "resuelta" if result["status"] == "reconciled" else row["status"],
            "cfdi_uuid": result.get("cfdi_uuid"),
        })
    return {"result": result, "ticket": _jd(updated)}
