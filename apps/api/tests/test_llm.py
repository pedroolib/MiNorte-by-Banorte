"""Wrapper LLM sin gastar: cliente OpenAI falso, lógica real de reintentos."""

import pytest

from app.agents import llm


class _Msg:
    def __init__(self, content="ok", tool_calls=None):
        self.content = content
        self.tool_calls = tool_calls or []


class _Resp:
    def __init__(self, msg):
        self.choices = [type("C", (), {"message": msg})()]


class FakeClient:
    """Falla la 1ª vez con el error dado, luego responde OK."""

    def __init__(self, error_vez1):
        self.error = error_vez1
        self.llamadas = []

        class _Completions:
            def __init__(self, outer):
                self.outer = outer

            def create(self, **kwargs):
                self.outer.llamadas.append(kwargs)
                if len(self.outer.llamadas) == 1:
                    raise Exception(self.outer.error)
                return _Resp(_Msg())

        class _Chat:
            def __init__(self, outer):
                self.completions = _Completions(outer)

        self.chat = _Chat(self)


def _parche(monkeypatch, error):
    fake = FakeClient(error)
    monkeypatch.setattr(llm, "_client", lambda: fake)
    return fake


def test_fallback_reasoning_effort_none(monkeypatch):
    fake = _parche(monkeypatch, "Function tools with reasoning_effort "
                                "are not supported for gpt-6-astra")
    defs = [llm.ToolDef("t", "d", {"type": "object", "properties": {}})]
    r = llm.chat([{"role": "user", "content": "hola"}], tools=defs,
                 model="gpt-6-astra", temperature=0.2)
    assert r.content == "ok"
    assert fake.llamadas[1].get("reasoning_effort") == "low"
    assert len(fake.llamadas) == 2


def test_fallback_sin_temperature(monkeypatch):
    fake = _parche(monkeypatch, "temperature does not support 0.2 "
                                "with this model. Only the default")
    r = llm.chat([{"role": "user", "content": "hola"}], model="x",
                 temperature=0.2)
    assert r.content == "ok"
    assert "temperature" not in fake.llamadas[1]


def test_error_no_adaptable_lanza(monkeypatch):
    fake = _parche(monkeypatch, "Error code: 401 - bad key")
    with pytest.raises(llm.LLMError, match="openai chat"):
        llm.chat([{"role": "user", "content": "hola"}], model="x")
    assert len(fake.llamadas) == 1  # sin reintento ciego


class _Fn:
    def __init__(self, call_id="c1", name="t", arguments="{}"):
        self.type = "function_call"
        self.call_id = call_id
        self.name = name
        self.arguments = arguments


class _Txt:
    def __init__(self, text):
        self.type = "output_text"
        self.text = text


class _MsgOut:
    def __init__(self, text):
        self.type = "message"
        self.content = [_Txt(text)]


class FakeResponses:
    def __init__(self, salidas):
        self.salidas = list(salidas)
        self.llamadas = []

        class _R:
            def __init__(self, outer):
                self.outer = outer

            def create(self, **kwargs):
                self.outer.llamadas.append(kwargs)
                out = self.outer.salidas.pop(0)
                return type("R", (), {"output": out})()

        self.responses = _R(self)


def test_responses_loop_ejecuta_tool(monkeypatch):
    import app.agents.llm as L

    fake = FakeResponses([[ _Fn("c1", "get_x", '{"a": 1}') ],
                          [ _MsgOut("listo 42") ]])
    monkeypatch.setattr(L, "_client", lambda: fake)
    defs = [L.ToolDef("get_x", "d", {"type": "object", "properties": {}})]
    texto, audit, trunc = L._responses_loop(
        "sys", [{"role": "user", "content": "hola"}], defs,
        lambda n, a: {"v": a["a"] + 1}, "m", 8)
    assert texto == "listo 42" and trunc is False
    assert audit[0]["tool"] == "get_x" and audit[0]["args"] == {"a": 1}
    assert fake.llamadas[0]["reasoning"] == {"effort": "low"}
    salida = fake.llamadas[1]["input"]
    assert salida[-1] == {"type": "function_call_output", "call_id": "c1",
                          "output": '{"v": 2}'}


def test_responses_loop_error_tool_corrige(monkeypatch):
    import app.agents.llm as L

    fake = FakeResponses([[ _Fn() ], [ _MsgOut("ok") ]])
    monkeypatch.setattr(L, "_client", lambda: fake)

    def _boom(n, a):
        raise ValueError("sin datos")

    defs = [L.ToolDef("t", "d", {"type": "object", "properties": {}})]
    texto, audit, _ = L._responses_loop("s", [], defs, _boom, "m", 8)
    assert texto == "ok" and audit[0]["error"] == "sin datos"
