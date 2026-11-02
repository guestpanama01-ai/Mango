"""Configuración global del asistente IA personal."""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

# Carga .env desde la raíz del proyecto (un nivel arriba de assistant/)
_ENV_PATH = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(_ENV_PATH)

# ---------------------------------------------------------------------------
# Modelos disponibles por proveedor
# ---------------------------------------------------------------------------
MODELS: dict[str, dict[str, str]] = {
    "claude": {
        "provider": "anthropic",
        "model": "claude-sonnet-4-5",
        "api_key_env": "ANTHROPIC_API_KEY",
    },
    "groq": {
        "provider": "groq",
        "model": "openai/gpt-oss-120b",
        "api_key_env": "GROQ_API_KEY",
    },
    "gemini": {
        "provider": "gemini",
        "model": "gemini-3.8-flash",
        "api_key_env": "GEMINI_API_KEY",
    },
}

# ---------------------------------------------------------------------------
# Constantes globales
# ---------------------------------------------------------------------------
MAX_ITERATIONS: int = 10
MAX_CONTEXT_TOKENS: int = 8000
TOOL_TIMEOUT_SECONDS: int = 30

DATA_DIR: Path = Path.home() / "assistant_data"
DATA_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH: Path = DATA_DIR / "memory.db"
LOG_PATH: Path = DATA_DIR / "assistant.log"


# ---------------------------------------------------------------------------
# Funciones
# ---------------------------------------------------------------------------
def get_api_key(alias: str) -> str | None:
    """Devuelve la API key del proveedor o None si no está configurada."""
    if alias not in MODELS:
        return None
    env_var = MODELS[alias]["api_key_env"]
    key = os.getenv(env_var, "").strip()
    return key or None


def available_providers() -> list[str]:
    """Lista de alias de proveedores con API key configurada."""
    return [alias for alias in MODELS if get_api_key(alias)]


def get_model(task_type: str) -> tuple[str, str]:
    """Elige proveedor y modelo según el tipo de tarea con fallback."""
    if task_type in {"code", "reasoning", "long"}:
        preferred = ["claude", "groq", "gemini"]
    else:  # "fast", "simple", "chat" o cualquier otro
        preferred = ["groq", "gemini", "claude"]

    for alias in preferred:
        if get_api_key(alias):
            return alias, MODELS[alias]["model"]

    raise RuntimeError(
        "No hay ningún proveedor con API key configurada. "
        "Añade al menos una en el archivo .env "
        "(GROQ_API_KEY, ANTHROPIC_API_KEY o GEMINI_API_KEY)."
    )


if __name__ == "__main__":
    print(f"Providers disponibles: {available_providers()}")
    try:
        alias, model = get_model("chat")
        print(f"get_model('chat') → ({alias!r}, {model!r})")
    except RuntimeError as e:
        print(f"ERROR: {e}")
