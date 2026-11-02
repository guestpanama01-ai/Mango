"""Loop del agente: LLM → tools → LLM hasta respuesta final."""
from __future__ import annotations

from typing import Optional

from assistant.config import MAX_ITERATIONS
from assistant.core.memory import (
    LongTermMemory,
    ShortTermMemory,
    TokenCounter,
    build_context,
)
from assistant.core.router import call_llm, stream_llm
from assistant.tools import registry

import assistant.tools.files  # noqa: F401
import assistant.tools.shell  # noqa: F401
import assistant.tools.web    # noqa: F401
import assistant.tools.memory_tool  # noqa: F401
import assistant.tools.utils  # noqa: F401
import assistant.tools.tasks  # noqa: F401

SYSTEM_PROMPT = """Eres un asistente personal en CLI. Respondes en español, de forma concisa y directa.

Tienes acceso a herramientas (tools). Úsalas cuando necesites información del sistema, archivos, web o ejecutar comandos.

Tienes herramientas de memoria. Si el usuario te pide que recuerdes algo (como su nombre, sus gustos o datos importantes), usa la herramienta 'remember_fact'. Para consultar lo que ya sabes sobre el usuario, usa 'list_facts'.

Tienes herramientas para gestionar recordatorios. Usa 'add_task' para recordar algo y 'list_tasks' para ver pendientes.

Reglas:
- No inventes datos. Si no sabes algo y una tool puede ayudarte, úsala.
- Para operaciones con archivos, usa siempre paths relativos al workspace.
- Si una tool devuelve error, explica el problema brevemente en vez de reintentar a ciegas.
- Cuando termines, da una respuesta final en texto (sin llamar más tools)."""


class Agent:
    """Agente con memoria, tools y loop de razonamiento."""

    def __init__(self) -> None:
        self.stm = ShortTermMemory()
        self.ltm = LongTermMemory()
        self.tc = TokenCounter()

    def _build_messages(self) -> list[dict]:
        """Construye contexto: system + hechos + historial reciente."""
        history = self.stm.get_context(limit=20)
        facts = self.ltm.all_facts()
        return build_context(SYSTEM_PROMPT, facts, history)

    def _log_result(self, result: dict) -> None:
        """Registra tokens usados en el contador."""
        total = result.get("tokens_in", 0) + result.get("tokens_out", 0)
        if total > 0:
            self.tc.log(
                provider=result.get("provider", "unknown"),
                model=result.get("model", "unknown"),
                tokens=total,
            )

    def run(self, user_message: str) -> str:
        """Procesa un mensaje del usuario y devuelve la respuesta final."""
        user_message = user_message.strip()
        if not user_message:
            return ""

        self.stm.add("user", user_message)
        schemas = registry.list_schemas()

        for iteration in range(MAX_ITERATIONS):
            messages = self._build_messages()
            try:
                result = call_llm(messages, tools=schemas, task_type="chat")
            except Exception as e:
                return f"Error llamando al LLM: {type(e).__name__}: {e}"

            self._log_result(result)
            tool_calls = result.get("tool_calls", [])
            text = result.get("text", "")

            if not tool_calls:
                self.stm.add("assistant", text or "(sin respuesta)")
                return text or "(sin respuesta)"

            if text:
                self.stm.add("assistant", text)

            for tc in tool_calls:
                name = tc["name"]
                args = tc["args"]
                tool_result = registry.execute(name, args)
                self.stm.add("user", f"[TOOL {name}] args={args}\n[RESULTADO]\n{tool_result}")

        return f"(límite de {MAX_ITERATIONS} iteraciones alcanzado sin respuesta final)"

    def run_stream(self, user_message: str):
        """Versión en streaming de run() para respuestas en tiempo real."""
        user_message = user_message.strip()
        if not user_message:
            yield ""
            return

        self.stm.add("user", user_message)
        messages = self._build_messages()
        
        # En esta versión simplificada, ignoramos tools para el streaming directo
        try:
            full_response = ""
            for chunk in stream_llm(messages):
                full_response += chunk
                yield chunk
            self.stm.add("assistant", full_response)
        except Exception as e:
            yield f"Error: {type(e).__name__}: {e}"


# Instancia global reutilizable
_default_agent: Optional[Agent] = None


def get_agent() -> Agent:
    """Devuelve instancia singleton del agente."""
    global _default_agent
    if _default_agent is None:
        _default_agent = Agent()
    return _default_agent


if __name__ == "__main__":
    agent = Agent()
    print("Tools registradas:", registry.tool_names())
    print(agent.run("Hola, ¿quién eres?"))