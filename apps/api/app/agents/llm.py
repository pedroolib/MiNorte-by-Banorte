"""Wrapper delgado OpenAI (T8): único punto vendor del proyecto.

- chat(): una llamada con historial + tools declaradas.
- chat_json(): respuesta JSON estricta contra schema (1 reintento).
- run_tool_loop(): loop agente→tool con límite de pasos y auditoría.
Sin frameworks. Para cambiar de vendor se reescribe este archivo.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from decimal import Decimal

from app.config import get_settings


class LLMError(RuntimeError):
    pass


@dataclass
class ToolDef:
    name: str
    description: str
    parameters: dict  # JSON Schema


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict


@dataclass
class ChatResult:
    content: str | None
    tool_calls: list[ToolCall] = field(default_factory=list)


def _client():
    key = get_settings().OPENAI_API_KEY
    if not key:
        raise LLMError("sin OPENAI_API_KEY en .env")
    from openai import OpenAI

    return OpenAI(api_key=key)


def _as_openai_tools(tools: list[ToolDef]) -> list[dict]:
    return [{"type": "function",
             "function": {"name": t.name, "description": t.description,
                          "parameters": t.parameters, "strict": True}}
            for t in tools]


def _to_result(msg) -> ChatResult:
    calls = []
    for tc in (msg.tool_calls or []):
        try:
            args = json.loads(tc.function.arguments or "{}")
        except json.JSONDecodeError as e:
            raise LLMError(f"args inválidos en {tc.function.name}: {e}")
        calls.append(ToolCall(id=tc.id, name=tc.function.name, arguments=args))
    return ChatResult(content=msg.content, tool_calls=calls)


def tool_model() -> str:
    """Modelo para loops con tools (puede no ser el de razonamiento)."""
    s = get_settings()
    return s.OPENAI_TOOL_MODEL or s.OPENAI_FAST_MODEL


def chat(messages: list[dict], tools: list[ToolDef] | None = None,
         model: str | None = None, temperature: float | None = None) -> ChatResult:
    """Una llamada. messages: [{role, content}]."""
    s = get_settings()
    kwargs: dict = {"model": model or s.OPENAI_FAST_MODEL, "messages": messages}
    if temperature is not None:
        kwargs["temperature"] = temperature
    try:
        resp = _client().chat.completions.create(
            **kwargs,
            tools=_as_openai_tools(tools) if tools else None,
        )
    except LLMError:
        raise
    except Exception as e:
        raise LLMError(f"openai chat: {e}") from e
    return _to_result(resp.choices[0].message)


def chat_json(messages: list[dict], schema: dict,
              model: str | None = None, strict: bool = True) -> dict:
    """JSON contra schema. Reintenta 1 vez; si falla, lanza.

    strict=False para schemas con objetos libres (props del Diseñador):
    el modo estricto de OpenAI exige additionalProperties:false en todo
    objeto, lo que prohibiría props con forma variable. La validación
    real la hace validate_choice en código, no el schema.
    """
    s = get_settings()
    modelo = model or s.OPENAI_REASONING_MODEL
    msgs = list(messages)
    for intento in range(2):
        try:
            resp = _client().chat.completions.create(
                model=modelo, messages=msgs,
                response_format={"type": "json_schema",
                                 "json_schema": {"name": "out", "schema": schema,
                                                 "strict": strict}},
            )
            return json.loads(resp.choices[0].message.content or "")
        except LLMError:
            raise
        except Exception as e:
            if intento == 1:
                raise LLMError(f"openai json: {e}") from e
            msgs = msgs + [{"role": "user",
                            "content": "Devuelve SOLO el JSON que pide el schema."}]
    raise LLMError("inalcanzable")


def run_tool_loop(system: str, history: list[dict], tools: list[ToolDef],
                  executor, model: str | None = None,
                  max_steps: int = 8, temperature: float | None = None) -> tuple[str, list[dict], bool]:
    """Loop agente→tool. Devuelve (respuesta, auditoría, truncado).

    executor(name, args) -> resultado JSON-serializable (lanza si falla;
    el error se devuelve al modelo para que se corrija).
    """
    s = get_settings()
    modelo = model or s.OPENAI_FAST_MODEL
    msgs = [{"role": "system", "content": system}] + list(history)
    audit: list[dict] = []
    import time
    for _ in range(max_steps):
        res = chat(msgs, tools, modelo, temperature)
        if not res.tool_calls:
            return res.content or "", audit, False
        msgs.append({"role": "assistant", "content": res.content or "",
                     "tool_calls": [{"id": tc.id, "type": "function",
                                     "function": {"name": tc.name,
                                                  "arguments": json.dumps(tc.arguments)}} for tc in res.tool_calls]})
        for tc in res.tool_calls:
            t0 = time.time()
            try:
                out = executor(tc.name, tc.arguments)
                audit.append({"tool": tc.name, "args": tc.arguments,
                              "ms": int((time.time() - t0) * 1000)})
                msgs.append({"role": "tool", "tool_call_id": tc.id,
                             "content": _json(out)})
            except Exception as e:
                audit.append({"tool": tc.name, "args": tc.arguments,
                              "ms": int((time.time() - t0) * 1000),
                              "error": str(e)[:200]})
                msgs.append({"role": "tool", "tool_call_id": tc.id,
                             "content": f"ERROR: {e}"})
    # sin pasos: cierre final sin tools
    fin = chat(msgs, None, modelo, temperature)
    return fin.content or "", audit, True


def _json(obj) -> str:
    def _d(o):
        if isinstance(o, Decimal):
            return str(o)
        if isinstance(o, dict):
            return {k: _d(v) for k, v in o.items()}
        if isinstance(o, (list, tuple)):
            return [_d(v) for v in o]
        return o
    return json.dumps(_d(obj), ensure_ascii=False, default=str)
