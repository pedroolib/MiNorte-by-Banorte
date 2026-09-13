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
    """Una llamada. messages: [{role, content}].

    Fallback automático para reasoning models (astra/sol): si el 400
    rechaza function tools con reasoning activo, reintenta con
    reasoning_effort='low' (mínimo que acepta tools); si rechaza
    temperature custom, reintenta sin ella. Así OPENAI_TOOL_MODEL puede
    ser un reasoning sin tocar agentes.
    """
    s = get_settings()
    kwargs: dict = {"model": model or s.OPENAI_FAST_MODEL, "messages": messages}
    if temperature is not None:
        kwargs["temperature"] = temperature
    if tools:
        kwargs["tools"] = _as_openai_tools(tools)
    for _ in range(3):
        try:
            resp = _client().chat.completions.create(**kwargs)
            return _to_result(resp.choices[0].message)
        except LLMError:
            raise
        except Exception as e:
            msg = str(e)
            if tools and "reasoning_effort" in msg and "reasoning_effort" not in kwargs:
                kwargs["reasoning_effort"] = "low"
                continue
            if "temperature" in msg and "temperature" in kwargs:
                del kwargs["temperature"]
                continue
            raise LLMError(f"openai chat: {e}") from e
    raise LLMError("inalcanzable")


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


def _as_responses_tools(tools: list[ToolDef]) -> list[dict]:
    return [{"type": "function", "name": t.name, "description": t.description,
             "parameters": t.parameters, "strict": True} for t in tools]


def _responses_text(output: list) -> str:
    partes = []
    for item in output or []:
        if getattr(item, "type", "") == "message":
            for b in (getattr(item, "content", None) or []):
                if getattr(b, "type", "") == "output_text":
                    partes.append(getattr(b, "text", "") or "")
    return "".join(partes)


def _responses_loop(system: str, history: list[dict], tools: list[ToolDef],
                    executor, modelo: str, max_steps: int):
    """Tool loop vía /v1/responses (reasoning que rechaza tools en chat).

    Misma auditoría que el loop de chat: [{tool, args, ms[, error]}].
    """
    import time

    entrada: list[dict] = [{"role": "system", "content": system}] + list(history)
    defs = _as_responses_tools(tools)
    audit: list[dict] = []
    for _ in range(max_steps):
        try:
            resp = _client().responses.create(
                model=modelo, input=entrada, tools=defs,
                reasoning={"effort": "low"},
            )
        except Exception as e:
            raise LLMError(f"openai responses: {e}") from e
        llamadas = [it for it in (resp.output or [])
                    if getattr(it, "type", "") == "function_call"]
        if not llamadas:
            return _responses_text(resp.output), audit, False
        # Reenviar TODA la salida (incluye reasoning): la API exige el item
        # reasoning junto a cada function_call que se le devuelva.
        entrada.extend(resp.output or [])
        for it in llamadas:
            try:
                args = json.loads(getattr(it, "arguments", None) or "{}")
            except json.JSONDecodeError as e:
                raise LLMError(f"args inválidos en {it.name}: {e}")
            t0 = time.time()
            try:
                out = executor(it.name, args)
                audit.append({"tool": it.name, "args": args,
                              "ms": int((time.time() - t0) * 1000)})
                entrada.append({"type": "function_call_output",
                                "call_id": it.call_id,
                                "output": _recorta(_json(out))})
            except Exception as e:
                audit.append({"tool": it.name, "args": args,
                              "ms": int((time.time() - t0) * 1000),
                              "error": str(e)[:200]})
                entrada.append({"type": "function_call_output",
                                "call_id": it.call_id,
                                "output": f"ERROR: {e}"})
    try:
        resp = _client().responses.create(
            model=modelo, input=entrada,
            reasoning={"effort": "low"},
        )
        return _responses_text(resp.output), audit, True
    except Exception as e:
        raise LLMError(f"openai responses: {e}") from e


def run_tool_loop(system: str, history: list[dict], tools: list[ToolDef],
                  executor, model: str | None = None,
                  max_steps: int = 8, temperature: float | None = None) -> tuple[str, list[dict], bool]:
    """Loop agente→tool. Devuelve (respuesta, auditoría, truncado).

    executor(name, args) -> resultado JSON-serializable (lanza si falla;
    el error se devuelve al modelo para que se corrija).
    """
    s = get_settings()
    modelo = model or s.OPENAI_FAST_MODEL
    if tools and s.OPENAI_TOOLS_API == "responses":
        return _responses_loop(system, history, tools, executor, modelo,
                               max_steps)
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
                             "content": _recorta(_json(out))})
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


#: Tope de caracteres por resultado de tool EN EL CONTEXTO (la auditoría
#: guarda completo para debug). Los outputs grandes (signals, merchants)
#: se reenvían en cada iteración del loop: sin tope, el input crece
#: ~output × iteraciones. El modelo puede pedir el dato filtrado si
#: necesita más (otra llamada con mejor args).
MAX_TOOL_CHARS = 4000


def _recorta(texto: str) -> str:
    if len(texto) <= MAX_TOOL_CHARS:
        return texto
    return (texto[:MAX_TOOL_CHARS]
            + f"\n...[truncado: {len(texto)} chars total; "
            "pide el dato filtrado con otra llamada]")
