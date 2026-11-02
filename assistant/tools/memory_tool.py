"""Herramientas para que el asistente guarde datos en su memoria a largo plazo."""
from assistant.tools.registry import tool
from assistant.core.memory import LongTermMemory

@tool(description="Guarda un dato importante sobre el usuario en tu memoria a largo plazo para recordarlo en el futuro.")
def remember_fact(key: str, value: str) -> str:
    """Guarda o actualiza un hecho en la base de datos."""
    ltm = LongTermMemory()
    ltm.set_fact(key, value)
    return f"OK: Recordaré que '{key}' es '{value}'."

@tool(description="Busca todos los datos que recuerdas sobre el usuario.")
def list_facts() -> str:
    """Devuelve una lista de todos los hechos guardados."""
    ltm = LongTermMemory()
    facts = ltm.all_facts()
    if not facts:
        return "No tengo ningún dato guardado sobre ti todavía."
    return "\n".join(f"- {k}: {v}" for k, v in facts.items())