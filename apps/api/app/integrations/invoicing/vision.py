"""Vision: ticket real -> JSON estricto (spec #3.3 caso 1, #19).

Único punto de extracción de tickets. Nunca calcula ni concilia (eso vive
en `financial/reconcile.py`); un campo no legible va `null`, nunca se
inventa (spec #18, principio "el motor calcula, los agentes interpretan").
"""

from __future__ import annotations

import base64

from app.agents import llm
from app.config import get_settings

EXTRACTION_SCHEMA = {
    "type": "object",
    "properties": {
        "comercio": {"type": ["string", "null"], "description": "Nombre del negocio impreso en el ticket"},
        "rfc_comercio": {"type": ["string", "null"], "description": "RFC del emisor si aparece impreso"},
        "total": {"type": ["string", "null"], "description": "Importe FINAL pagado, Decimal como string, ej. '162.40'"},
        "fecha": {"type": ["string", "null"], "description": "Fecha/hora del ticket en ISO 8601"},
        "folio": {"type": ["string", "null"], "description": "Folio/ticket/transacción impreso"},
        "portal_facturacion": {"type": ["string", "null"],
                               "description": "URL/dominio del portal de autofacturación si aparece impreso"},
        "confianza": {"type": "string", "enum": ["alta", "media", "baja"]},
        "campos_no_legibles": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["comercio", "rfc_comercio", "total", "fecha", "folio",
                 "portal_facturacion", "confianza", "campos_no_legibles"],
    "additionalProperties": False,
}

SYSTEM = (
    "Extrae SOLO lo que puedas leer literalmente de la foto de un ticket "
    "de compra mexicano. Nunca inventes ni calcules cifras que no estén "
    "impresas. Si un campo no es legible o no aparece, va null y agrégalo "
    "a campos_no_legibles (nunca lo adivines).\n\n"
    "TOTAL: es el monto que realmente se cobró (el que coincide con "
    "'SU CAMBIO', 'CARNET D ENTREGADO' o 'TOTAL IMPORTE DE VENTA' al pie "
    "del ticket). Muchos tickets mexicanos imprimen VARIAS líneas de total "
    "en este orden: 'TOTAL VENTA' (antes de redondeo) -> 'REDONDEO' -> "
    "'TOTAL' (el cobrado de verdad). Si ves más de una, usa SIEMPRE la "
    "ÚLTIMA / la de más abajo — nunca la primera 'TOTAL VENTA'. Ejemplo: "
    "'TOTAL VENTA 162.40' + 'REDONDEO 0.60' + 'TOTAL 163.00' -> total=163.00.\n\n"
    "FECHA: los tickets mexicanos SIEMPRE imprimen la fecha en formato "
    "DD/MM/AA o DD/MM/AAAA (día PRIMERO, nunca mes primero). Ej.: "
    "'06/09/26 09:59' es el 6 de septiembre de 2026, 09:59 — "
    "NO el 9 de junio ni ningún otro año. Un año de 2 dígitos 'AA' es "
    "20AA (26 -> 2026), nunca 19AA. Devuelve fecha ISO 8601 completa con "
    "la hora si aparece (ej. '2026-09-06T09:59:00'); si no hay hora usa "
    "T00:00:00. No confundas la fecha del ticket con ninguna otra fecha "
    "impresa (vencimiento de puntos, promociones, etc.).\n\n"
    "FOLIO: es el identificador de LA VENTA/TICKET, normalmente junto a la "
    "etiqueta 'Folio:' o 'No. Ticket' (ej. 'Folio: 0022936'). NO es "
    "'NO DE ARTICULOS' / 'ARTICULOS' (esa es la cantidad de productos "
    "comprados, no un folio), ni el número de autorización de la tarjeta, "
    "ni el código de barras. Si hay varios números parecidos, usa el que "
    "esté explícitamente etiquetado como folio/ticket/transacción.\n\n"
    "'rfc_comercio' solo si un RFC aparece impreso en el ticket.\n\n"
    "PORTAL_FACTURACION: casi todos los tickets mexicanos imprimen dónde "
    "autofacturar, normalmente cerca de un QR con una etiqueta como "
    "'Facturas:', 'Facturación:' o 'Factura tu compra en'. Copia el "
    "dominio/URL tal como está impreso (ej. 'alsuper.com/facturacion'). "
    "Si no ves ninguna leyenda de facturación en el ticket, null — no "
    "inventes ni adivines un dominio a partir del nombre del comercio."
)


def extract_receipt(image_bytes: bytes, mime: str = "image/jpeg",
                    model: str | None = None) -> dict:
    """Ticket (bytes de foto) -> dict validable contra ReceiptExtraction.

    Usa Gemini si hay GEMINI_API_KEY configurada (alcance de T-tickets,
    no toca el resto de la app); si no, OpenAI como siempre."""
    if get_settings().GEMINI_API_KEY:
        from app.integrations.invoicing import gemini_llm

        return gemini_llm.chat_json(
            SYSTEM, EXTRACTION_SCHEMA, text="Extrae los datos de este ticket.",
            image_bytes=image_bytes, mime=mime, model=model)

    b64 = base64.b64encode(image_bytes).decode("ascii")
    messages = [
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": [
            {"type": "text", "text": "Extrae los datos de este ticket."},
            {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}},
        ]},
    ]
    modelo = model or get_settings().OPENAI_VISION_MODEL
    return llm.chat_json(messages, EXTRACTION_SCHEMA, model=modelo)
