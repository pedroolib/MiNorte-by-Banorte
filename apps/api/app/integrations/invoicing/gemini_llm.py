"""Wrapper delgado para Gemini (Google GenAI) — SOLO para el flujo de
tickets (Vision + Browser Agent), a propósito acotado: no toca
`app/agents/llm.py` (compartido con Consultor/Analista/Diseñador).

No se manda `response_schema`: nuestros esquemas están en formato
OpenAI-strict (`"type": ["string", "null"]`), que Gemini no acepta tal
cual. En vez de mantener dos copias de cada esquema, se describe el JSON
esperado en el prompt (`response_mime_type="application/json"` ya fuerza
JSON válido) y se valida/reintenta acá — mismo principio que
`agents/llm.py.chat_json`: un reintento con corrección antes de fallar.
"""

from __future__ import annotations

import json

from app.config import get_settings


class GeminiError(RuntimeError):
    pass


def _client():
    key = get_settings().GEMINI_API_KEY
    if not key:
        raise GeminiError("sin GEMINI_API_KEY en .env")
    from google import genai

    return genai.Client(api_key=key)


def _schema_hint(schema: dict) -> str:
    """Descripción legible del JSON pedido, derivada del mismo esquema
    que ya usamos para OpenAI (una sola fuente de verdad por campo)."""
    lines = []
    for name, spec in schema.get("properties", {}).items():
        t = spec.get("type")
        bit = f'  "{name}": {t}'
        if spec.get("enum"):
            bit += f" (uno de: {spec['enum']})"
        if spec.get("description"):
            bit += f" — {spec['description']}"
        lines.append(bit)
    return "\n".join(lines)


def chat_json(system: str, schema: dict, *, text: str | None = None,
             image_bytes: bytes | None = None, mime: str = "image/jpeg",
             model: str | None = None) -> dict:
    """Una tarea, JSON validado contra `schema['required']` (reintenta 1
    vez con corrección). `image_bytes` opcional para Vision."""
    from google.genai import types

    modelo = model or get_settings().GEMINI_MODEL
    required = schema.get("required", [])
    instructions = (
        f"{system}\n\nResponde SOLO un objeto JSON válido (sin texto "
        "fuera del JSON, sin ``` ni comentarios) con EXACTAMENTE estas "
        f"claves:\n{_schema_hint(schema)}"
    )

    parts = [types.Part.from_text(text=instructions)]
    if text:
        parts.append(types.Part.from_text(text=text))
    if image_bytes:
        parts.append(types.Part.from_bytes(data=image_bytes, mime_type=mime))

    client = _client()
    last_err: Exception | None = None
    for intento in range(2):
        try:
            resp = client.models.generate_content(
                model=modelo, contents=parts,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json", temperature=0),
            )
            raw = (resp.text or "").strip()
            data = json.loads(raw)
            faltantes = [k for k in required if k not in data]
            if faltantes:
                raise ValueError(f"faltan claves en la respuesta: {faltantes}")
            return data
        except GeminiError:
            raise
        except Exception as e:
            last_err = e
            parts.append(types.Part.from_text(
                text=("Tu respuesta anterior no cumplió el formato "
                     f"pedido ({e}). Corrige y responde SOLO el JSON "
                     "con exactamente esas claves.")))
    raise GeminiError(f"gemini json: {last_err}")
