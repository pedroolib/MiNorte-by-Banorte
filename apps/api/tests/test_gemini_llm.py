"""Gemini wrapper (T-tickets, alcance acotado): JSON por prompt + reintento,
sin gastar la API real (cliente mockeado). Sigue el mismo contrato que
agents/llm.chat_json: valida required, reintenta 1 vez, falla explícito."""

from __future__ import annotations

import pytest

from app.integrations.invoicing import gemini_llm as gm

SCHEMA = {
    "type": "object",
    "properties": {
        "comercio": {"type": ["string", "null"], "description": "nombre"},
        "total": {"type": ["string", "null"]},
    },
    "required": ["comercio", "total"],
    "additionalProperties": False,
}


class FakeResponse:
    def __init__(self, text):
        self.text = text


class FakeModels:
    def __init__(self, texts):
        self._texts = iter(texts)
        self.calls = []

    def generate_content(self, model, contents, config):
        self.calls.append({"model": model, "contents": contents, "config": config})
        return FakeResponse(next(self._texts))


class FakeClient:
    def __init__(self, texts):
        self.models = FakeModels(texts)


def test_sin_api_key_lanza_gemini_error(monkeypatch):
    # gemini_llm importó `get_settings` a su propio namespace (from ...
    # import ...): hay que parchear ESE nombre, no app.config.get_settings.
    monkeypatch.setattr(gm, "get_settings", lambda: type(
        "S", (), {"GEMINI_API_KEY": "", "GEMINI_MODEL": "gemini-2.5-flash"})())
    with pytest.raises(gm.GeminiError):
        gm._client()


def test_chat_json_exito_primer_intento(monkeypatch):
    fake = FakeClient(['{"comercio": "ALSUPER", "total": "163.00"}'])
    monkeypatch.setattr(gm, "_client", lambda: fake)
    out = gm.chat_json("system", SCHEMA, text="extrae")
    assert out == {"comercio": "ALSUPER", "total": "163.00"}
    assert len(fake.models.calls) == 1


def test_chat_json_reintenta_si_faltan_claves(monkeypatch):
    fake = FakeClient([
        '{"comercio": "ALSUPER"}',  # falta "total": inválido
        '{"comercio": "ALSUPER", "total": "163.00"}',  # corregido
    ])
    monkeypatch.setattr(gm, "_client", lambda: fake)
    out = gm.chat_json("system", SCHEMA, text="extrae")
    assert out == {"comercio": "ALSUPER", "total": "163.00"}
    assert len(fake.models.calls) == 2


def test_chat_json_reintenta_si_no_es_json_valido(monkeypatch):
    fake = FakeClient(["esto no es json", '{"comercio": "X", "total": "1"}'])
    monkeypatch.setattr(gm, "_client", lambda: fake)
    out = gm.chat_json("system", SCHEMA, text="extrae")
    assert out == {"comercio": "X", "total": "1"}


def test_chat_json_falla_tras_dos_intentos(monkeypatch):
    fake = FakeClient(["no json", "sigue sin ser json"])
    monkeypatch.setattr(gm, "_client", lambda: fake)
    with pytest.raises(gm.GeminiError):
        gm.chat_json("system", SCHEMA, text="extrae")


def test_chat_json_con_imagen_manda_bytes(monkeypatch):
    fake = FakeClient(['{"comercio": "X", "total": "1"}'])
    monkeypatch.setattr(gm, "_client", lambda: fake)
    gm.chat_json("system", SCHEMA, image_bytes=b"fake-jpeg-bytes", mime="image/jpeg")
    contents = fake.models.calls[0]["contents"]
    assert len(contents) == 2  # instrucciones + imagen (sin texto extra)
