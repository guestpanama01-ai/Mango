"""Tools de sistema de archivos con sandbox en DATA_DIR."""
from __future__ import annotations

from pathlib import Path

from assistant.config import DATA_DIR
from assistant.tools.registry import tool

# Sandbox: todo acceso queda restringido a DATA_DIR/workspace
WORKSPACE: Path = DATA_DIR / "workspace"
WORKSPACE.mkdir(parents=True, exist_ok=True)

MAX_READ_BYTES: int = 200_000  # ~200 KB


def _safe_path(relative: str) -> Path:
    """Resuelve path relativo dentro del workspace. Lanza ValueError si escapa."""
    # Normaliza y resuelve
    target = (WORKSPACE / relative).resolve()
    workspace_resolved = WORKSPACE.resolve()
    # Verifica que esté dentro del workspace
    try:
        target.relative_to(workspace_resolved)
    except ValueError:
        raise ValueError(f"Path fuera del workspace: {relative}")
    return target


@tool(description="Lista archivos y carpetas dentro del workspace")
def list_files(path: str = ".") -> str:
    """Lista el contenido de un directorio del workspace."""
    try:
        target = _safe_path(path)
    except ValueError as e:
        return f"Error: {e}"

    if not target.exists():
        return f"Error: no existe '{path}'"
    if not target.is_dir():
        return f"Error: '{path}' no es un directorio"

    entries = []
    for p in sorted(target.iterdir()):
        kind = "dir" if p.is_dir() else "file"
        size = p.stat().st_size if p.is_file() else 0
        entries.append(f"[{kind}] {p.name}" + (f" ({size} bytes)" if kind == "file" else ""))

    if not entries:
        return "(vacío)"
    return "\n".join(entries)


@tool(description="Lee un archivo de texto del workspace")
def read_file(path: str) -> str:
    """Lee el contenido de un archivo del workspace."""
    try:
        target = _safe_path(path)
    except ValueError as e:
        return f"Error: {e}"

    if not target.exists():
        return f"Error: no existe '{path}'"
    if not target.is_file():
        return f"Error: '{path}' no es un archivo"

    size = target.stat().st_size
    if size > MAX_READ_BYTES:
        return f"Error: archivo demasiado grande ({size} bytes, máx {MAX_READ_BYTES})"

    try:
        return target.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return f"Error: '{path}' no es texto UTF-8"
    except Exception as e:
        return f"Error leyendo '{path}': {type(e).__name__}: {e}"


@tool(description="Escribe texto en un archivo del workspace (crea carpetas si faltan)")
def write_file(path: str, content: str) -> str:
    """Escribe contenido en un archivo del workspace."""
    try:
        target = _safe_path(path)
    except ValueError as e:
        return f"Error: {e}"

    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return f"OK: escrito '{path}' ({len(content)} chars)"
    except Exception as e:
        return f"Error escribiendo '{path}': {type(e).__name__}: {e}"


@tool(description="Añade texto al final de un archivo del workspace")
def append_file(path: str, content: str) -> str:
    """Añade contenido a un archivo del workspace."""
    try:
        target = _safe_path(path)
    except ValueError as e:
        return f"Error: {e}"

    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("a", encoding="utf-8") as f:
            f.write(content)
        return f"OK: añadido a '{path}' ({len(content)} chars)"
    except Exception as e:
        return f"Error añadiendo a '{path}': {type(e).__name__}: {e}"


@tool(description="Borra un archivo del workspace")
def delete_file(path: str) -> str:
    """Borra un archivo del workspace. No borra directorios."""
    try:
        target = _safe_path(path)
    except ValueError as e:
        return f"Error: {e}"

    if not target.exists():
        return f"Error: no existe '{path}'"
    if target.is_dir():
        return f"Error: '{path}' es un directorio (no soportado)"
    try:
        target.unlink()
        return f"OK: borrado '{path}'"
    except Exception as e:
        return f"Error borrando '{path}': {type(e).__name__}: {e}"


if __name__ == "__main__":
    print("WORKSPACE:", WORKSPACE)
    print(write_file("test/hola.txt", "hola mundo"))
    print(read_file("test/hola.txt"))
    print(append_file("test/hola.txt", "\nsegunda línea"))
    print(read_file("test/hola.txt"))
    print(list_files("test"))
    print(read_file("../fuera.txt"))  # debe fallar (sandbox)
    print(delete_file("test/hola.txt"))
    print("OK files")
