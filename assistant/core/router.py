"""Router multi-proveedor: elige LLM y hace la llamada con fallback."""
from __future__ import annotations

import json
import time
import re
from typing import Optional, Generator

from assistant.config import MODELS, get_api_key, get_model

# ---------------------------------------------------------------------------
# Clasificador simple de tareas (Router Inteligente)
# ---------------------------------------------------------------------------
def detect_task_type(message: str) -> str:
    """Analiza el texto para decidir si es código, razonamiento o chat normal."""
    code_keywords = ["def ", "class ", "import ", "function", "código", "script", "```"]
    reasoning_keywords = ["razona", "explica", "por qué", "analiza", "compara", "lógica"]
    
    msg_lower = message.lower()
    
    if any(kw in message for kw in code_keywords):
        return "code"
    if any(kw in msg_lower for kw in reasoning_keywords):
        return "reasoning"
    return "chat"

# ---------------------------------------------------------------------------
# Funciones auxiliares
# ---------------------------------------------------------------------------
def _tools_anthropic(schemas: list[dict]) -> list[dict]:
    return schemas

def _tools_openai(schemas: list[dict]) -> list[dict]:
    out = []
    for s in schemas:
        out.append({
            "type": "function",
            "function": {
                "name": s["name"],
                "description": s.get("description", ""),
                "parameters": s["input_schema"],
            },
        })
    return out

def _tools_gemini(schemas: list[dict]) -> list[dict]:
    out = []
    for s in schemas:
        out.append({
            "name": s["name"],
            "description": s.get("description", ""),
            "parameters": s["input_schema"],
        })
    return out

# ---------------------------------------------------------------------------
# Llamadas por proveedor
# ---------------------------------------------------------------------------
def _call_anthropic(model: str, messages: list[dict], tools: list[dict]) -> dict:
    from anthropic import Anthropic
    client = Anthropic(api_key=get_api_key("claude"))
    system_text = None
    if messages and messages[0]["role"] == "system":
        system_text = messages[0]["content"]

    resp = client.messages.create(
        model=model, max_tokens=2048, system=system_text,
        messages=[m for m in messages if m["role"] != "system"],
        tools=_tools_anthropic(tools) if tools else [],
    )
    text_parts = []
    tool_calls = []
    for block in resp.content:
        if block.type == "text": text_parts.append(block.text)
        elif block.type == "tool_use":
            tool_calls.append({"id": block.id, "name": block.name, "args": block.input})
    return {
        "text": "\n".join(text_parts).strip(), "tool_calls": tool_calls,
        "stop_reason": resp.stop_reason, "tokens_in": resp.usage.input_tokens,
        "tokens_out": resp.usage.output_tokens, "provider": "anthropic", "model": model,
    }

def _call_groq(model: str, messages: list[dict], tools: list[dict]) -> dict:
    from groq import Groq
    client = Groq(api_key=get_api_key("groq"))
    kwargs = {"model": model, "messages": messages, "max_tokens": 2048}
    if tools:
        kwargs["tools"] = _tools_openai(tools)
        kwargs["tool_choice"] = "auto"

    resp = client.chat.completions.create(**kwargs)
    choice = resp.choices[0]
    msg = choice.message
    tool_calls = []
    if msg.tool_calls:
        for tc in msg.tool_calls:
            try: args = json.loads(tc.function.arguments)
            except json.JSONDecodeError: args = {}
            tool_calls.append({"id": tc.id, "name": tc.function.name, "args": args})
    return {
        "text": (msg.content or "").strip(), "tool_calls": tool_calls,
        "stop_reason": choice.finish_reason,
        "tokens_in": resp.usage.prompt_tokens if resp.usage else 0,
        "tokens_out": resp.usage.completion_tokens if resp.usage else 0,
        "provider": "groq", "model": model,
    }

def _call_gemini(model: str, messages: list[dict], tools: list[dict]) -> dict:
    import google.generativeai as genai
    genai.configure(api_key=get_api_key("gemini"))
    system_text = ""
    contents = []
    for m in messages:
        if m["role"] == "system": system_text = m["content"]
        else:
            role = "user" if m["role"] == "user" else "model"
            contents.append({"role": role, "parts": [{"text": m["content"]}]})
    gemini_tools = [{"function_declarations": _tools_gemini(tools)}] if tools else None
    gen_model = genai.GenerativeModel(model_name=model, system_instruction=system_text or None, tools=gemini_tools)
    resp = gen_model.generate_content(contents)
    text_parts = []
    tool_calls = []
    if resp.candidates and resp.candidates[0].content.parts:
        for i, part in enumerate(resp.candidates[0].content.parts):
            if hasattr(part, "function_call") and part.function_call:
                fc = part.function_call
                tool_calls.append({"id": f"gemini_{i}", "name": fc.name, "args": dict(fc.args)})
            elif hasattr(part, "text") and part.text:
                text_parts.append(part.text)
    usage = getattr(resp, "usage_metadata", None)
    return {
        "text": "\n".join(text_parts).strip(), "tool_calls": tool_calls,
        "stop_reason": "tool_use" if tool_calls else "end_turn",
        "tokens_in": getattr(usage, "prompt_token_count", 0) if usage else 0,
        "tokens_out": getattr(usage, "candidates_token_count", 0) if usage else 0,
        "provider": "gemini", "model": model,
    }

_CALLERS = {"anthropic": _call_anthropic, "groq": _call_groq, "gemini": _call_gemini}

# ---------------------------------------------------------------------------
# API pública
# ---------------------------------------------------------------------------
def call_llm(messages: list[dict], tools: Optional[list[dict]] = None, task_type: str = "chat") -> dict:
    tools = tools or []
    
    # Router: Si es código o razonamiento, prefiere Gemini (o el que tengas), si es chat, Groq
    if task_type in {"code", "reasoning"}:
        order = ["gemini", "groq"]
    else:
        order = ["groq", "gemini"]

    available = [a for a in order if get_api_key(a)]
    if not available:
        raise RuntimeError("No hay ningún proveedor con API key. Configura .env.")

    last_error: Optional[Exception] = None
    
    for alias in available:
        provider = MODELS[alias]["provider"]
        model = MODELS[alias]["model"]
        caller = _CALLERS[provider]

        # Reintentos con Backoff (3 intentos)
        for attempt in range(3):
            try:
                return caller(model, messages, tools)
            except Exception as e:
                last_error = e
                if "429" in str(e) or "rate limit" in str(e).lower():
                    time.sleep(2 ** attempt) # Espera 1s, 2s, 4s
                else:
                    break # Si no es error de límite, pasa al siguiente proveedor

    raise RuntimeError(f"Todos los proveedores fallaron. Último error: {type(last_error).__name__}: {last_error}")

def stream_llm(messages: list[dict], tools: Optional[list[dict]] = None) -> Generator[str, None, None]:
    """Generador que produce la respuesta del LLM en tiempo real (solo Groq)."""
    from groq import Groq
    alias = "groq"
    if not get_api_key(alias):
        raise RuntimeError("Groq no está configurado.")
    
    client = Groq(api_key=get_api_key(alias))
    kwargs = {
        "model": MODELS[alias]["model"],
        "messages": messages,
        "max_tokens": 2048,
        "stream": True,
    }
    if tools:
        kwargs["tools"] = _tools_openai(tools)
        kwargs["tool_choice"] = "auto"

    stream = client.chat.completions.create(**kwargs)
    for chunk in stream:
        if chunk.choices[0].delta.content:
            yield chunk.choices[0].delta.content

def get_llm_choice(task_type: str = "chat") -> tuple[str, str]:
    return get_model(task_type)