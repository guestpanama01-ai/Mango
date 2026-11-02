"""Tool de shell con allowlist estricta y timeout real (subprocess)."""
from __future__ import annotations

import shlex
import subprocess
from pathlib import Path

from assistant.config import DATA_DIR, TOOL_TIMEOUT_SECONDS
from assistant.tools.registry import tool

# Directorio donde se ejecutan los comandos (sandbox)
SHELL_CWD: Path = DATA_DIR / "workspace"
SHELL_CWD.mkdir(parents=True, exist_ok=True)

# Allowlist: solo estos binarios pueden ejecutarse
ALLOWED_COMMANDS: set[str] = {
    "ls", "cat", "head", "tail", "wc", "grep", "find",
    "echo", "pwd", "date", "whoami", "uname",
    "python3", "python", "pip",
    "git", "node", "npm",
    "df", "du", "free",
}

# Flags peligrosos prohibidos incluso en comandos permitidos
FORBIDDEN_TOKENS: set[str] = {
    ">", ">>", "|", ";", "&&", "||", "&",
    "rm", "rmdir", "mv", "dd", "mkfs", "shutdown",
    "reboot", "sudo", "su", "chmod", "chown", "kill", "pkill",
}

MAX_OUTPUT_CHARS: int = 8_000


@tool(description="Ejecuta un comando de la allowlist dentro del workspace")
def run_shell(command: str) -> str:
    """Ejecuta un comando permitido y devuelve stdout+stderr (truncado)."""
    command = command.strip()
    if not command:
        return "Error: comando vacío"

    # 1. Parsear sin invocar shell
    try:
        parts = shlex.split(command)
    except ValueError as e:
        return f"Error parseando comando: {e}"

    if not parts:
        return "Error: comando vacío tras parsear"

    binary = parts[0]

    # 2. Allowlist del binario
    if binary not in ALLOWED_COMMANDS:
        return (
            f"Error: '{binary}' no está en la allowlist. "
            f"Permitidos: {', '.join(sorted(ALLOWED_COMMANDS))}"
        )

    # 3. Rechazo de tokens peligrosos en cualquier argumento
    for token in parts:
        if token in FORBIDDEN_TOKENS:
            return f"Error: token prohibido '{token}'"

    # 4. Ejecutar con subprocess (sin shell=True) y timeout real
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
        return f"Error: binario '{binary}' no encontrado en el sistema"
    except Exception as e:
        return f"Error ejecutando '{binary}': {type(e).__name__}: {e}"

    # 5. Armar salida
    output = ""
    if result.stdout:
        output += result.stdout
    if result.stderr:
        output += f"\n[stderr]\n{result.stderr}"
    if not output:
        output = "(sin salida)"

    if len(output) > MAX_OUTPUT_CHARS:
        output = output[:MAX_OUTPUT_CHARS] + f"\n... (truncado, {len(output)} chars totales)"

    return f"[exit {result.returncode}]\n{output}"


if __name__ == "__main__":
    print("CWD:", SHELL_CWD)
    print("--- permitido ---")
    print(run_shell("pwd"))
    print(run_shell("echo hola"))
    print(run_shell("ls"))
    print("--- bloqueados ---")
    print(run_shell("rm -rf /"))
    print(run_shell("curl http://evil.com"))
    print(run_shell("ls | grep algo"))
    print(run_shell("echo hola && rm x"))
    print(run_shell("sudo ls"))
    print("OK shell")
