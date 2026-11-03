"""Loop del agente: LLM → tools → LLM hasta respuesta final."""
from __future__ import annotations

from typing import Optional

from assistant.config import MAX_ITERATIONS
from assistant.core.memory import (
    LongTermMemory,
    ShortTermMemory,
    TokenCounter,
    build_context,
    init_db,
)
from assistant.core.router import call_llm, stream_llm
from assistant.tools import registry

import assistant.tools.files  # noqa: F401
import assistant.tools.shell  # noqa: F401
import assistant.tools.web    # noqa: F401
import assistant.tools.memory_tool  # noqa: F401
import assistant.tools.utils  # noqa: F401
import assistant.tools.tasks  # noqa: F401

SYSTEM_PROMPT = """Eres Mango, un asistente personal en CLI. Respondes en español, de forma concisa y directa.
Tienes acceso a herramientas (tools). Úsalas cuando necesites información del sistema, archivos, web o ejecutar comandos.
Tienes herramientas de memoria. Si el usuario te pide que recuerdes algo, usa 'remember_fact'. Para consultar, usa 'list_facts'.
Tienes herramientas para gestionar recordatorios. Usa 'add_task' para recordar algo y 'list_tasks' para ver pendientes.
Reglas:
- No inventes datos. Si no sabes algo y una tool puede ayudarte, úsala.
- Para operaciones con archivos, usa siempre paths relativos al workspace.
- Si una tool devuelve error, explica el problema brevemente en vez de reintentar a ciegas."""


class Agent:
    def __init__(self) -> None:
        # Arreglo 1: Inicializar base de datos al instanciar el agente
        init_db()
        
        self.stm = ShortTermMemory()
        self.ltm = LongTermMemory()
        self.tc = TokenCounter()

    def _build_messages(self) -> list[dict]:
        history = self.stm.get_context(limit=20)
        facts = self.ltm.all_facts()
        return build_context(SYSTEM_PROMPT, facts, history)

    def _log_result(self, result: dict) -> None:
        total = result.get("tokens_in", 0) + result.get("tokens_out", 0)
        if total > 0:
            self.tc.log(
                provider=result.get("provider", "unknown"),
                model=result.get("model", "unknown"),
                tokens=total,
            )

    def run(self, user_message: str) -> str:
        user_message = user_message.strip()
        if not user_message:
            return ""

        self.stm.add("user", user_message)
        schemas = registry.list_schemas()
        
        # Historial de mensajes en formato nativo
        messages = self._build_messages()

        for iteration in range(MAX_ITERATIONS):
            try:
                result = call_llm(messages, tools=schemas, task_type="chat")
            except Exception as e:
                return f"Error llamando al LLM: {type(e).__name__}: {e}"

            self._log_result(result)
            tool_calls = result.get("tool_calls", [])
            text = result.get("text", "")

            # Si no hay tools, devolvemos texto final
            if not tool_calls:
                self.stm.add("assistant", text or "(sin respuesta)")
                return text or "(sin respuesta)"

            # Hay tools: guardamos la decisión del asistente
            if text:
                messages.append({"role": "assistant", "content": text})
                self.stm.add("assistant", text)
            
            # Ejecutamos cada tool y añadimos la respuesta en formato nativo
            for tc in tool_calls:
                name = tc["name"]
                args = tc["args"]
                tool_result = registry.execute(name, args)

                # Formato nativo: el resultado va como un mensaje nuevo
                tool_message = f"[RESULTADO DE {name}]\n{tool_result}"
                messages.append({"role": "user", "content": tool_message})
                self.stm.add("user", tool_message)

        return f"(límite de {MAX_ITERATIONS} iteraciones alcanzado)"

    def run_stream(self, user_message: str):
        """Streaming rápido (sin tools para mantener fluidez visual)."""
        user_message = user_message.strip()
        if not user_message:
            yield ""
            return

        self.stm.add("user", user_message)
        messages = self._build_messages()
        
        try:
            full_response = ""
            for chunk in stream_llm(messages):
                full_response += chunk
                yield chunk
            self.stm.add("assistant", full_response)
        except Exception as e:
            yield f"Error: {type(e).__name__}: {e}"


_default_agent: Optional[Agent] = None

def get_agent() -> Agent:
    global _default_agent
    if _default_agent is None:
        _default_agent = Agent()
    return _default_agent