"""Tool de shell con allowlist estricta, sandbox y timeout real (subprocess)."""
from __future__ import annotations

import shlex
import subprocess
from pathlib import Path

from assistant.config import DATA_DIR, TOOL_TIMEOUT_SECONDS
from assistant.tools.registry import tool

SHELL_CWD: Path = DATA_DIR / "workspace"
SHELL_CWD.mkdir(parents=True, exist_ok=True)

# Allowlist: solo estos binarios
ALLOWED_COMMANDS: set[str] = {
    "ls", "cat", "head", "tail", "wc", "grep", "find",
    "echo", "pwd", "date", "whoami", "uname",
    "python3", "git", "df", "du", "free",
}

# Flags peligrosos prohibidos
FORBIDDEN_TOKENS: set[str] = {
    ">", ">>", "|", ";", "&&", "||", "&",
    "rm", "rmdir", "mv", "dd", "mkfs", "shutdown",
    "reboot", "sudo", "su", "chmod", "chown", "kill", "pkill",
}

# Caracteres prohibidos en los argumentos (evita ejecución de código, paths absolutos e inyecciones)
FORBIDDEN_CHARS: set[str] = {";", "&", "|", "$", "`", "\\", "/", ".."}

MAX_OUTPUT_CHARS: int = 8_000

@tool(description="Ejecuta un comando de la allowlist dentro del workspace")
def run_shell(command: str) -> str:
    command = command.strip()
    if not command:
        return "Error: comando vacío"

    try:
        parts = shlex.split(command)
    except ValueError as e:
        return f"Error parseando comando: {e}"

    if not parts:
        return "Error: comando vacío tras parsear"

    binary = parts[0]

    if binary not in ALLOWED_COMMANDS:
        return f"Error: '{binary}' no está en la allowlist."

    # Validación estricta de argumentos
    for token in parts[1:]:
        if token in FORBIDDEN_TOKENS:
            return f"Error: token prohibido '{token}'"
        if any(char in token for char in FORBIDDEN_CHARS):
            return f"Error: carácter prohibido en el argumento '{token}'"
        # Bloquear flags de python3 que ejecutan código
        if binary == "python3" and token in {"-c", "-m", "-i", "-"}:
            return f"Error: flag de Python prohibido '{token}'"

    try:
        result = subprocess.run(
            parts,
            cwd=str(SHELL_CWD),
            capture_output=True,
            text=True,
            timeout=TOOL_TIMEOUT_SECONDS,
            shell=False,
        )
    except subprocess.TimeoutExpired:
        return f"Error: timeout de {TOOL_TIMEOUT_SECONDS}s ejecutando '{binary}'"
    except FileNotFoundError:
        return f"Error: binario '{binary}' no encontrado"
    except Exception as e:
        return f"Error ejecutando '{binary}': {type(e).__name__}: {e}"

    output = ""
    if result.stdout: output += result.stdout
    if result.stderr: output += f"\n[stderr]\n{result.stderr}"
    if not output: output = "(sin salida)"

    if len(output) > MAX_OUTPUT_CHARS:
        output = output[:MAX_OUTPUT_CHARS] + f"\n... (truncado)"

    return f"[exit {result.returncode}]\n{output}"