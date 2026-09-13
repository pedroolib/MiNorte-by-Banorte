"""Contrato de acciones del Browser Agent (spec #19).

Acciones base del spec: navigate, fill, click, select, scroll, go_back,
finish, request_user_input. Se agregó `download` (mismo principio: un
`ref` real, nunca coordenadas) para poder capturar el XML del CFDI que
el portal ofrece tras emitir la factura y conciliarlo de verdad en vez
de solo confirmar visualmente que "se ve" emitida.

Prohibido: coordenadas. El agente decide sobre labels/roles de elementos
interactivos reales de la página (accesibilidad), nunca sobre pixeles.
"""

from __future__ import annotations

BrowserActionName = (
    "navigate", "fill", "click", "select", "scroll", "go_back",
    "download", "finish", "request_user_input",
)

# Botones/labels que representan una acción externa irreversible (spec:
# "confirmación antes de una acción final irreversible"). Heurística por
# palabra clave sobre el label visible + type=submit como señal fuerte.
#
# OJO: en un portal DE facturación, casi todo botón menciona "factura"
# (navegar a la sección, "Facturar" en el home, etc.) — por eso NO se
# usan solas palabras genéricas como "facturar"/"emitir"/"pagar": eso
# bloquea navegación inofensiva pidiendo confirmación humana en cada
# clic. Solo frases que describen la acción FINAL de verdad.
IRREVERSIBLE_KEYWORDS = (
    "enviar solicitud", "confirmar solicitud", "confirmar y enviar",
    "solicitar factura", "generar factura", "confirmar factura",
    "timbrar factura", "timbrar", "enviar factura", "finalizar factura",
    "aceptar y facturar", "aceptar y enviar", "generar cfdi",
)

ACTION_SCHEMA = {
    "type": "object",
    "properties": {
        "action": {"type": "string", "enum": list(BrowserActionName)},
        "ref": {"type": ["string", "null"],
                "description": "ref del elemento interactivo listado (fill/click/select)"},
        "value": {"type": ["string", "null"],
                  "description": "texto a escribir/seleccionar, o URL para navigate"},
        "source_field": {
            "type": ["string", "null"],
            "description": (
                "SOLO para fill/select: la clave EXACTA de invoice_data de "
                "donde salió `value` (ej. 'cp_receptor'). El servidor "
                "verifica que invoice_data[source_field] == value antes de "
                "escribir — nunca inventes ni reutilices el valor de otro "
                "campo; si no hay una clave real que lo respalde, usa "
                "request_user_input en vez de fill/select.")},
        "missing_field": {"type": ["string", "null"],
                          "description": "solo si action=request_user_input: qué dato falta"},
        "reason": {"type": "string", "description": "por qué esta acción, breve"},
    },
    "required": ["action", "ref", "value", "source_field", "missing_field", "reason"],
    "additionalProperties": False,
}


def is_irreversible(decision: dict, elements: list[dict]) -> bool:
    """¿Esta decisión requiere confirmación humana antes de ejecutarse?"""
    if decision.get("action") != "click":
        return False
    el = next((e for e in elements if e.get("ref") == decision.get("ref")), None)
    if el is None:
        return True  # target desconocido: tratar como irreversible por seguridad
    if (el.get("type") or "").lower() == "submit":
        return True
    label = (el.get("label") or "").lower()
    return any(k in label for k in IRREVERSIBLE_KEYWORDS)
