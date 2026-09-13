"""Browser Agent (spec #3.3 caso 1, #19): navega un portal REAL de
facturación con el mismo agente para distintos comercios.

Diseño:
- Observación = elementos interactivos reales (rol, label, tipo) vía
  Playwright, NUNCA coordenadas.
- Decisión = una llamada a OpenAI (JSON estricto, `browser/actions.py`)
  por paso, con límite de pasos.
- Frenos obligatorios: CAPTCHA, formulario de auth inesperado, dato
  faltante (`request_user_input`), límite de pasos.
- Toda acción irreversible (heurística en `actions.is_irreversible`) se
  detiene en `esperando_confirmacion` y espera una llamada explícita a
  `confirm()` — nunca se autoconfirma.

Las sesiones viven en memoria del proceso (demo de una sola compañía,
mismo patrón que los `lru_cache` singleton de `app/data.py`): mantener el
`Page` de Playwright vivo entre `start()` y `confirm()` evita tener que
serializar un browser real.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

from app.agents import llm
from app.browser.actions import ACTION_SCHEMA, is_irreversible

DEFAULT_MAX_STEPS = 20
INTERACTIVE_SELECTOR = (
    "a[href], button, input, select, textarea, "
    "[role=button], [role=link], [role=checkbox], [role=radio], [role=tab]"
)

TERMINAL_STATUSES = {
    "bloqueada_captcha", "bloqueada_auth", "bloqueada_datos_faltantes",
    "bloqueada_limite_pasos", "cancelada", "resuelta", "fallida",
}


class BrowserAgentError(RuntimeError):
    pass


@dataclass
class ActiveSession:
    id: str
    portal_url: str
    invoice_data: dict[str, Any]
    playwright: Any
    browser: Any
    page: Any
    max_steps: int = DEFAULT_MAX_STEPS
    steps: list[dict] = field(default_factory=list)
    status: str = "navegando"
    pending_action: dict | None = None
    downloaded_xml: str | None = None

    def public_state(self) -> dict:
        return {
            "id": self.id, "portal_url": self.portal_url, "status": self.status,
            "steps": self.steps, "pending_action": self.pending_action,
            "n_steps": len(self.steps), "max_steps": self.max_steps,
            "has_downloaded_xml": self.downloaded_xml is not None,
        }


_SESSIONS: dict[str, ActiveSession] = {}


# Nombre accesible real de un campo: la mayoría de los formularios reales
# (Wansoft incluido) ponen el texto en un <label> aparte, no en
# aria-label/placeholder del <input> — leer solo esos dos dejaba al
# agente sin forma de distinguir campos vecinos (así se le cruzaron
# "Correo electrónico" y "CP": ambos llegaban con label="" al modelo).
_LABEL_JS = """
(e) => {
  function labelFor(el) {
    const al = el.getAttribute('aria-label');
    if (al && al.trim()) return al.trim();
    const labelledby = el.getAttribute('aria-labelledby');
    if (labelledby) {
      const t = labelledby.split(/\\s+/)
        .map(id => document.getElementById(id)?.textContent || '').join(' ').trim();
      if (t) return t;
    }
    if (el.id) {
      try {
        const lab = document.querySelector(`label[for="${CSS.escape(el.id)}"]`);
        if (lab && lab.textContent.trim()) return lab.textContent.trim();
      } catch (err) {}
    }
    const wrap = el.closest('label');
    if (wrap && wrap.textContent.trim()) return wrap.textContent.trim();
    const ph = el.getAttribute('placeholder');
    if (ph && ph.trim()) return ph.trim();
    const title = el.getAttribute('title');
    if (title && title.trim()) return title.trim();
    if (el.tagName === 'INPUT' && (el.type === 'submit' || el.type === 'button') && el.value) {
      return el.value.trim();
    }
    const txt = (el.innerText || el.textContent || '').trim();
    return txt;
  }
  // Valor actual: muchos portales prellenan campos por su cuenta desde la
  // propia URL (ej. Wansoft arma el "Código de factura" desde el QR del
  // ticket) — sin verlo, el agente lo sobreescribía con datos que YA
  // tenía, rompiendo el campo (así se rompió el lookup del ticket real).
  let value = '';
  if (e.tagName === 'SELECT') {
    value = e.options[e.selectedIndex]?.text || e.value || '';
  } else if ('value' in e) {
    value = e.value || '';
  }
  // ¿de verdad está a la vista, o hay un modal/overlay encima? is_visible
  // de Playwright solo mira CSS (display/opacity/tamaño), no si algo lo
  // TAPA — así el agente seguía viendo "EMITIR FACTURA" y el resto del
  // formulario viejo detrás del modal real de éxito ("El documento se
  // generó exitosamente"), se confundía y lo intentaba enviar de nuevo.
  const r = e.getBoundingClientRect();
  const cx = r.left + r.width / 2, cy = r.top + r.height / 2;
  const topmost = document.elementFromPoint(cx, cy);
  const covered = !(topmost === e || e.contains(topmost) || (topmost && topmost.contains(e)));
  return {
    tag: e.tagName.toLowerCase(),
    role: e.getAttribute('role') || e.tagName.toLowerCase(),
    type: e.getAttribute('type') || '',
    label: labelFor(e).slice(0, 80),
    value: String(value).slice(0, 80),
    covered,
  };
}
"""


async def _snapshot(page) -> list[dict]:
    """Elementos interactivos reales: rol, label, tipo, valor actual. Sin
    coordenadas."""
    els = page.locator(INTERACTIVE_SELECTOR)
    n = await els.count()
    out: list[dict] = []
    for i in range(min(n, 60)):
        el = els.nth(i)
        try:
            if not await el.is_visible():
                continue
        except Exception:
            continue
        ref = str(i)
        try:
            await el.evaluate("(e, ref) => e.setAttribute('data-minorte-ref', ref)", ref)
            info = await el.evaluate(_LABEL_JS)
        except Exception:
            continue
        if info["covered"]:
            # tapado por un modal/overlay real (ej. el diálogo de éxito
            # encima del formulario viejo): no es una opción real ahora
            continue
        out.append({"ref": ref, "tag": info["tag"], "role": info["role"],
                   "label": info["label"], "type": info["type"],
                   "value": info["value"]})
    return out


CAPTCHA_WIDGET_SELECTOR = (
    "iframe[src*='recaptcha'], iframe[src*='hcaptcha'], "
    "div.g-recaptcha, div.h-captcha, iframe[title*='captcha' i]"
)


async def _has_captcha(page) -> bool:
    """Un widget de CAPTCHA REALMENTE visible bloqueando al usuario —
    no cualquier mención de 'captcha' en el HTML. Muchos sitios cargan
    el badge invisible de reCAPTCHA v3 (scoring de spam en segundo plano,
    sin reto visible) en TODA página; buscar la palabra en el HTML crudo
    lo confundía con un freno real y detenía el agente sin necesidad."""
    try:
        widgets = page.locator(CAPTCHA_WIDGET_SELECTOR)
        n = await widgets.count()
        for i in range(min(n, 5)):
            if await widgets.nth(i).is_visible():
                return True
        return False
    except Exception:
        return False


async def _has_unexpected_auth(page, invoice_data: dict) -> bool:
    if invoice_data.get("credenciales"):
        return False
    try:
        return await page.locator("input[type=password]").count() > 0
    except Exception:
        return False


SYSTEM = (
    "Eres un agente que llena el formulario de facturación de un portal "
    "REAL de un comercio, usando SOLO los datos de invoice_data. Nunca "
    "inventes RFC, montos, fechas ni folios que no estén en invoice_data. "
    "Una acción por turno, siempre sobre un `ref` de la lista de "
    "elementos_interactivos (nunca coordenadas). Cada elemento trae su "
    "`value` actual: si YA tiene un valor no vacío, el portal lo puso "
    "solo (ej. un código de ticket/factura que arma él mismo desde la "
    "URL/QR) — NO lo toques ni lo sobreescribas con datos de "
    "invoice_data, aunque se parezcan a otro campo. Solo llena un campo "
    "si su `value` actual está vacío. "
    "En fill/select, `source_field` es OBLIGATORIO y debe ser la clave "
    "real de invoice_data cuyo valor copiaste EXACTO a `value` — el "
    "servidor lo verifica y rechaza el llenado si no coincide, así que "
    "nunca pongas ahí el valor de un campo distinto (ej. usar la razón "
    "social para llenar el CP) ni un dato inventado. "
    "Un campo del formulario necesita un valor de invoice_data que sea "
    "null, vacío, o que la clave ni siquiera exista: en CUALQUIERA de "
    "esos tres casos responde action=request_user_input con "
    "missing_field — NUNCA dejes el campo vacío, lo saltes en silencio, "
    "ni le pongas el valor de OTRO campo solo porque el de verdad falta, "
    "aunque el campo no sea obligatorio en el formulario (ej. 'correo "
    "electrónico' sin asterisco: si el portal lo pide, pídelo tú "
    "también). Solo usa un valor de invoice_data si es un string real y "
    "no vacío, y siempre con su `source_field` correcto. "
    "Si el formulario ya está completo, NO respondas finish: haz click en "
    "el botón final (enviar/generar/emitir factura) como cualquier otra "
    "acción — un humano lo aprueba antes de que se ejecute de verdad, así "
    "que no lo evites. "
    "Si tras emitir la factura aparece un enlace/botón para descargar el "
    "XML (o CFDI, o comprobante fiscal digital) — NO el PDF —, usa "
    "action=download sobre ese elemento: eso completa la conciliación "
    "real, no solo confirma visualmente que se emitió. "
    "Responde action=finish SOLO cuando ya descargaste el XML, o cuando "
    "la pantalla de éxito no ofrece ningún XML descargable (solo PDF o "
    "envío por correo) y de verdad no hay nada más que hacer aquí."
)


def _decide(url: str, title: str, elements: list[dict], invoice_data: dict,
           history: list[dict], model: str | None = None) -> dict:
    """Usa Gemini si hay GEMINI_API_KEY configurada (alcance de
    T-tickets); si no, OpenAI como siempre."""
    import json as _json

    from app.config import get_settings

    payload = {
        "url": url, "title": title,
        "elementos_interactivos": elements,
        "invoice_data": invoice_data,
        "historial_reciente": history[-6:],
    }
    user_content = _json.dumps(payload, ensure_ascii=False, default=str)

    if get_settings().GEMINI_API_KEY:
        from app.integrations.invoicing import gemini_llm

        return gemini_llm.chat_json(SYSTEM, ACTION_SCHEMA, text=user_content, model=model)

    messages = [
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": user_content},
    ]
    return llm.chat_json(messages, ACTION_SCHEMA, model=model or llm.tool_model())


def _looks_like_xml(filename: str, head: bytes) -> bool:
    if filename.lower().endswith(".xml"):
        return True
    return b"<cfdi:Comprobante" in head or b"<?xml" in head[:100]


async def _apply(sess: "ActiveSession", decision: dict) -> str:
    page = sess.page
    action = decision["action"]
    ref = decision.get("ref")
    value = decision.get("value")
    locator = page.locator(f"[data-minorte-ref='{ref}']") if ref is not None else None
    if action == "navigate":
        if not value:
            raise BrowserAgentError("navigate sin value")
        await page.goto(value, wait_until="domcontentloaded")
        return f"navigate -> {value}"
    if action == "fill":
        if locator is None:
            raise BrowserAgentError("fill sin ref")
        await locator.fill(value or "", timeout=8000)
        return f"fill[{ref}] = {value!r}"
    if action == "click":
        if locator is None:
            raise BrowserAgentError("click sin ref")
        # timeout corto (no el default de 30s de Playwright) para que un
        # ref obsoleto falle rápido en vez de colgar la request entera;
        # 15s (más que fill/select) porque un botón final real puede
        # deshabilitarse un momento al hacer clic (anti doble-envío) antes
        # de quedar clickeable de nuevo o navegar — visto en vivo contra
        # un portal real (Wansoft): "EMITIR FACTURA" tardó más de 8s.
        await locator.click(timeout=15000)
        try:
            await page.wait_for_load_state("domcontentloaded", timeout=5000)
        except Exception:
            pass
        return f"click[{ref}]"
    if action == "select":
        if locator is None:
            raise BrowserAgentError("select sin ref")
        await locator.select_option(value, timeout=8000)
        return f"select[{ref}] = {value!r}"
    if action == "scroll":
        await page.mouse.wheel(0, 800)
        return "scroll"
    if action == "go_back":
        await page.go_back()
        return "go_back"
    if action == "download":
        if locator is None:
            raise BrowserAgentError("download sin ref")
        # Clic real (no coordenadas) sobre el enlace/botón de descarga;
        # Playwright intercepta la descarga del navegador directamente,
        # sin depender de dónde la guarde el sistema operativo.
        async with page.expect_download(timeout=15000) as dl_info:
            await locator.click(timeout=15000)
        download = await dl_info.value
        path = await download.path()
        content = path.read_bytes() if path else b""
        filename = download.suggested_filename or "descarga"
        if _looks_like_xml(filename, content[:200]):
            sess.downloaded_xml = content.decode("utf-8", errors="replace")
            return f"download -> {filename} ({len(content)} bytes, XML capturado)"
        return f"download -> {filename} ({len(content)} bytes, no es XML)"
    raise BrowserAgentError(f"acción no ejecutable directamente: {action}")


async def _advance(sess: ActiveSession, model: str | None = None) -> None:
    """Corre pasos hasta un freno: bloqueo, confirmación pendiente o fin."""
    while len(sess.steps) < sess.max_steps:
        if await _has_captcha(sess.page):
            sess.status = "bloqueada_captcha"
            return
        if await _has_unexpected_auth(sess.page, sess.invoice_data):
            sess.status = "bloqueada_auth"
            return
        elements = await _snapshot(sess.page)
        decision = await asyncio.to_thread(
            _decide, sess.page.url, await sess.page.title(), elements,
            sess.invoice_data, sess.steps, model)

        if decision["action"] == "request_user_input":
            sess.status = "bloqueada_datos_faltantes"
            sess.pending_action = decision
            return
        if decision["action"] == "finish":
            sess.status = "resuelta"
            return
        if decision["action"] in ("fill", "select"):
            src = decision.get("source_field")
            real = sess.invoice_data.get(src) if src else None
            if not src or real != decision.get("value"):
                # el modelo quiso escribir algo que NO viene de verdad de
                # invoice_data (inventado, o el valor de OTRO campo) — se
                # rechaza en código, no se confía en que el prompt baste
                # (así se coló "PUBLICO EN GENERAL" dentro del campo CP).
                sess.status = "bloqueada_datos_faltantes"
                sess.pending_action = {
                    **decision, "missing_field": src or decision.get("ref"),
                    "reason": ("el valor propuesto no coincide con "
                              f"invoice_data[{src!r}] — rechazado antes de escribirlo"),
                }
                return
        if is_irreversible(decision, elements):
            # el `reason` es la paráfrasis del modelo; adjuntar el elemento
            # real (label/type) para que la confirmación humana sea
            # informada y no un salto de fe sobre lo que dice la IA.
            target = next((e for e in elements if e.get("ref") == decision.get("ref")), None)
            sess.status = "esperando_confirmacion"
            sess.pending_action = {**decision, "target": target}
            return

        result = await _apply(sess, decision)
        sess.steps.append({"index": len(sess.steps), "url": sess.page.url,
                           "action": decision, "result": result})
    sess.status = "bloqueada_limite_pasos"


async def start(session_id: str, portal_url: str, invoice_data: dict[str, Any], *,
                headless: bool = True, max_steps: int = DEFAULT_MAX_STEPS,
                model: str | None = None) -> ActiveSession:
    if session_id in _SESSIONS:
        await close(session_id)
    from playwright.async_api import async_playwright

    pw = await async_playwright().start()
    browser = await pw.chromium.launch(
        headless=headless, args=["--no-sandbox", "--disable-dev-shm-usage"])
    page = await browser.new_page()
    sess = ActiveSession(id=session_id, portal_url=portal_url, invoice_data=invoice_data,
                         playwright=pw, browser=browser, page=page, max_steps=max_steps)
    _SESSIONS[session_id] = sess
    try:
        await page.goto(portal_url, wait_until="domcontentloaded")
        await _advance(sess, model)
    except Exception as e:
        sess.status = "fallida"
        sess.pending_action = {"error": str(e)[:300]}
    return sess


async def confirm(session_id: str, approve: bool, *, model: str | None = None) -> ActiveSession:
    sess = _SESSIONS.get(session_id)
    if sess is None:
        raise BrowserAgentError(f"sesión no existe (¿ya cerró?): {session_id}")
    if sess.status != "esperando_confirmacion":
        raise BrowserAgentError(f"nada pendiente de confirmar (status={sess.status})")
    if not approve:
        sess.status = "cancelada"
        await close(session_id)
        return sess
    decision = sess.pending_action
    try:
        result = await _apply(sess, decision)
        sess.steps.append({"index": len(sess.steps), "url": sess.page.url,
                           "action": decision, "result": result, "confirmado_por_humano": True})
        sess.pending_action = None
        sess.status = "navegando"
        await _advance(sess, model)
    except Exception as e:
        sess.status = "fallida"
        sess.pending_action = {"error": str(e)[:300]}
    return sess


RESUMABLE_STATUSES = {"bloqueada_captcha", "bloqueada_limite_pasos", "fallida"}


async def resume(session_id: str, *, extra_steps: int = 0, model: str | None = None) -> ActiveSession:
    """Reanuda tras un freno que un humano ya resolvió por su cuenta:
    resolvió el CAPTCHA a mano en la ventana visible (`headless=False`),
    decide dejar seguir más allá del límite de pasos, o quiere reintentar
    tras un error técnico transitorio (`fallida`, ej. un botón que tarda
    en reactivarse tras un primer clic). La página sigue viva: se toma
    un snapshot fresco y el modelo decide de nuevo, no repite ciegamente
    la acción que falló.

    NO reanuda `bloqueada_auth`: ese freno es intencional (spec #19,
    "detenerse ante autenticación no soportada") y no se levanta solo."""
    sess = _SESSIONS.get(session_id)
    if sess is None:
        raise BrowserAgentError(f"sesión no existe (¿ya cerró?): {session_id}")
    if sess.status not in RESUMABLE_STATUSES:
        raise BrowserAgentError(f"no se puede reanudar desde status={sess.status}")
    if extra_steps > 0:
        sess.max_steps += extra_steps
    sess.status = "navegando"
    try:
        await _advance(sess, model)
    except Exception as e:
        sess.status = "fallida"
        sess.pending_action = {"error": str(e)[:300]}
    return sess


async def provide_input(session_id: str, field: str, value: str, *,
                        model: str | None = None) -> ActiveSession:
    """Resuelve un `request_user_input` (spec #19): un humano da el dato
    que Vision no pudo leer y el agente sigue desde donde se quedó.

    El dato entra a `invoice_data` como cualquier otro campo real: el
    agente nunca lo distingue de lo que vino del ticket."""
    sess = _SESSIONS.get(session_id)
    if sess is None:
        raise BrowserAgentError(f"sesión no existe (¿ya cerró?): {session_id}")
    if sess.status != "bloqueada_datos_faltantes":
        raise BrowserAgentError(f"no hay dato pendiente que rellenar (status={sess.status})")
    sess.invoice_data = {**sess.invoice_data, field: value}
    sess.pending_action = None
    sess.status = "navegando"
    try:
        await _advance(sess, model)
    except Exception as e:
        sess.status = "fallida"
        sess.pending_action = {"error": str(e)[:300]}
    return sess


def get(session_id: str) -> ActiveSession | None:
    return _SESSIONS.get(session_id)


async def screenshot(session_id: str) -> bytes:
    """Captura de la página REAL en este momento (spec #5: "sensación de
    que los agentes están trabajando") — funciona corriendo headless, sin
    necesitar la ventana visible. Solo mientras la sesión sigue viva
    (se pierde al cerrar/terminar el proceso, igual que el resto del
    estado en memoria)."""
    sess = _SESSIONS.get(session_id)
    if sess is None:
        raise BrowserAgentError(f"sesión no existe (¿ya cerró?): {session_id}")
    return await sess.page.screenshot(full_page=True)


async def close(session_id: str) -> None:
    sess = _SESSIONS.pop(session_id, None)
    if sess is None:
        return
    try:
        await sess.browser.close()
    except Exception:
        pass
    try:
        await sess.playwright.stop()
    except Exception:
        pass
