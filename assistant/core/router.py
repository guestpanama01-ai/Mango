"""Router multi-proveedor: elige LLM y hace la llamada con fallback."""
from __future__ import annotations

import json
from typing import Optional

from assistant.config import MODELS, get_api_key, get_model


# ---------------------------------------------------------------------------
# Normalización de schemas de tools al formato de cada proveedor
# ---------------------------------------------------------------------------

def _tools_anthropic(schemas: list[dict]) -> list[dict]:
    """Los schemas ya están en formato Anthropic."""
    return schemas


def _tools_openai(schemas: list[dict]) -> list[dict]:
    """Convierte schemas Anthropic → formato OpenAI/Groq."""
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
    """Convierte schemas Anthropic → formato Gemini function_declarations."""
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
    """Llama a Claude y normaliza la respuesta."""
    from anthropic import Anthropic

    client = Anthropic(api_key=get_api_key("claude"))
    system_text = None
    if messages and messages[0]["role"] == "system":
        system_text = messages[0]["content"]

    resp = client.messages.create(
        model=model,
        max_tokens=2048,
        system=system_text,
        messages=[m for m in messages if m["role"] != "system"],
        tools=_tools_anthropic(tools) if tools else [],
    )

    text_parts: list[str] = []
    tool_calls: list[dict] = []
    for block in resp.content:
        if block.type == "text":
            text_parts.append(block.text)
        elif block.type == "tool_use":
            tool_calls.append({
                "id": block.id,
                "name": block.name,
                "args": block.input,
            })

    return {
        "text": "\n".join(text_parts).strip(),
        "tool_calls": tool_calls,
        "stop_reason": resp.stop_reason,
        "tokens_in": resp.usage.input_tokens,
        "tokens_out": resp.usage.output_tokens,
        "provider": "anthropic",
        "model": model,
    }


def _call_groq(model: str, messages: list[dict], tools: list[dict]) -> dict:
    """Llama a Groq y normaliza la respuesta."""
    from groq import Groq

    client = Groq(api_key=get_api_key("groq"))
    resp = client.chat.completions.create(
        model=model,
        messages=messages,
        tools=_tools_openai(tools) if tools else None,
        tool_choice="auto" if tools else "none",
        max_tokens=2048,
    )

    choice = resp.choices[0]
    msg = choice.message
    tool_calls: list[dict] = []
    if msg.tool_calls:
        for tc in msg.tool_calls:
            try:
                args = json.loads(tc.function.arguments)
            except json.JSONDecodeError:
                args = {}
            tool_calls.append({
                "id": tc.id,
                "name": tc.function.name,
                "args": args,
            })

    return {
        "text": (msg.content or "").strip(),
        "tool_calls": tool_calls,
        "stop_reason": choice.finish_reason,
        "tokens_in": resp.usage.prompt_tokens if resp.usage else 0,
        "tokens_out": resp.usage.completion_tokens if resp.usage else 0,
        "provider": "groq",
        "model": model,
    }


def _call_gemini(model: str, messages: list[dict], tools: list[dict]) -> dict:
    """Llama a Gemini y normaliza la respuesta."""
    import google.generativeai as genai

    genai.configure(api_key=get_api_key("gemini"))

    system_text = ""
    contents: list[dict] = []
    for m in messages:
        if m["role"] == "system":
            system_text = m["content"]
        else:
            role = "user" if m["role"] == "user" else "model"
            contents.append({"role": role, "parts": [{"text": m["content"]}]})

    gemini_tools = [{"function_declarations": _tools_gemini(tools)}] if tools else None

    gen_model = genai.GenerativeModel(
        model_name=model,
        system_instruction=system_text or None,
        tools=gemini_tools,
    )

    resp = gen_model.generate_content(contents)

    text_parts: list[str] = []
    tool_calls: list[dict] = []
    if resp.candidates and resp.candidates[0].content.parts:
        for i, part in enumerate(resp.candidates[0].content.parts):
            if hasattr(part, "function_call") and part.function_call:
                fc = part.function_call
                tool_calls.append({
                    "id": f"gemini_{i}",
                    "name": fc.name,
                    "args": dict(fc.args),
                })
            elif hasattr(part, "text") and part.text:
                text_parts.append(part.text)

    usage = getattr(resp, "usage_metadata", None)
    return {
        "text": "\n".join(text_parts).strip(),
        "tool_calls": tool_calls,
        "stop_reason": "tool_use" if tool_calls else "end_turn",
        "tokens_in": getattr(usage, "prompt_token_count", 0) if usage else 0,
        "tokens_out": getattr(usage, "candidates_token_count", 0) if usage else 0,
        "provider": "gemini",
        "model": model,
    }


_CALLERS = {
    "anthropic": _call_anthropic,
    "groq": _call_groq,
    "gemini": _call_gemini,
}


# ---------------------------------------------------------------------------
# API pública
# ---------------------------------------------------------------------------

def call_llm(
    messages: list[dict],
    tools: Optional[list[dict]] = None,
    task_type: str = "chat",
) -> dict:
    """
    Llama al LLM con fallback entre proveedores.

    Args:
        messages: lista de {"role": "system|user|assistant", "content": str}
        tools: schemas de tools (formato Anthropic)
        task_type: "chat", "code", "reasoning", etc.

    Returns:
        dict con text, tool_calls, stop_reason, tokens_in, tokens_out, provider, model
    """
    tools = tools or []

    if task_type in {"code", "reasoning", "long"}:
        order = ["claude", "groq", "gemini"]
    else:
        order = ["groq", "gemini", "claude"]

    available = [a for a in order if get_api_key(a)]
    if not available:
        raise RuntimeError(
            "No hay ningún proveedor con API key. Configura .env."
        )

    last_error: Optional[Exception] = None
    for alias in available:
        provider = MODELS[alias]["provider"]
        model = MODELS[alias]["model"]
        caller = _CALLERS[provider]

        try:
            return caller(model, messages, tools)
        except Exception as e:
            last_error = e
            continue

    raise RuntimeError(
        f"Todos los proveedores fallaron. Último error: "
        f"{type(last_error).__name__}: {last_error}"
    )


def get_llm_choice(task_type: str = "chat") -> tuple[str, str]:
    """Devuelve (alias, model) que se usaría para un task_type dado."""
    return get_model(task_type)


if __name__ == "__main__":
    print("Probando call_llm con task_type='chat'...")
    try:
        resp = call_llm(
            messages=[{"role": "user", "content": "Responde solo: OK"}],
            task_type="chat",
        )
        print(f"Provider: {resp['provider']}")
        print(f"Model: {resp['model']}")
        print(f"Text: {resp['text']}")
        print(f"Tokens: in={resp['tokens_in']} out={resp['tokens_out']}")
        print("OK router")
    except Exception as e:
        print(f"ERROR: {type(e).__name__}: {e}")
