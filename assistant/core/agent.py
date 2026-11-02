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
from assistant.core.router import call_llm
from assistant.tools import registry

# Importamos todas las herramientas al inicio para que se registren
# antes de que el agente empiece a trabajar.
import assistant.tools.files  # noqa: F401
import assistant.tools.shell  # noqa: F401
import assistant.tools.web    # noqa: F401
import assistant.tools.memory_tool  # noqa: F401
import assistant.tools.utils

SYSTEM_PROMPT = """Eres un asistente personal en CLI. Respondes en español, de forma concisa y directa.

Tienes acceso a herramientas (tools). Úsalas cuando necesites información del sistema, archivos, web o ejecutar comandos.

Tienes herramientas de memoria. Si el usuario te pide que recuerdes algo (como su nombre, sus gustos o datos importantes), usa la herramienta 'remember_fact'. Para consultar lo que ya sabes sobre el usuario, usa 'list_facts'.

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
        """
        Procesa un mensaje del usuario y devuelve la respuesta final.

        Loop:
        1. Guarda mensaje del usuario en memoria
        2. Construye contexto
        3. Llama LLM con tools disponibles
        4. Si hay tool_calls: ejecuta cada uno, añade resultados al historial, repite
        5. Si no hay tool_calls: devuelve texto y guarda en memoria
        """
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

            # Sin tool_calls → respuesta final
            if not tool_calls:
                self.stm.add("assistant", text or "(sin respuesta)")
                return text or "(sin respuesta)"

            # Hay tool_calls: guardar el "pensamiento" y ejecutar tools
            if text:
                self.stm.add("assistant", text)

            for tc in tool_calls:
                name = tc["name"]
                args = tc["args"]
                tool_result = registry.execute(name, args)

                # Registra el resultado de la tool en el historial
                # (como mensaje de "user" para que el LLM lo vea)
                self.stm.add(
                    "user",
                    f"[TOOL {name}] args={args}\n[RESULTADO]\n{tool_result}",
                )

        # Se agotaron las iteraciones
        return f"(límite de {MAX_ITERATIONS} iteraciones alcanzado sin respuesta final)"


# Instancia global reutilizable
_default_agent: Optional[Agent] = None


def get_agent() -> Agent:
    """Devuelve instancia singleton del agente."""
    global _default_agent
    if _default_agent is None:
        _default_agent = Agent()
    return _default_agent


if __name__ == "__main__":
    # Bloque de pruebas por si ejecutas `python -m assistant.core.agent`
    agent = Agent()
    print("Tools registradas:", registry.tool_names())
    print()
    print("=== Test: saludo ===")
    print(agent.run("Hola, ¿quién eres?"))
    print()
    print("OK agent")