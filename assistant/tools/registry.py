"""Registro de tools con schema JSON autogenerado."""
from __future__ import annotations

import inspect
import json
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
from typing import Any, Callable, Optional

TYPES_MAP: dict[str, str] = {
    "str": "string",
    "int": "integer",
    "float": "number",
    "bool": "boolean",
    "list": "array",
    "dict": "object",
}


TOOL_REGISTRY: dict[str, dict] = {}


def _py_type_to_json(annotation: Any) -> str:
    """Traduce type hint Python (str o tipo) a tipo JSON Schema."""
    if annotation is inspect.Parameter.empty:
        return "string"

    # Con `from __future__ import annotations`, todo llega como string
    if isinstance(annotation, str):
        base = annotation
        # Optional[X] / Union[X, None] / X | None
        if "|" in base:
            parts = [p.strip() for p in base.split("|") if p.strip() != "None"]
            base = parts[0] if parts else "str"
        elif base.startswith("Optional["):
            base = base[len("Optional["):-1].strip()
        elif base.startswith("Union["):
            inner = base[len("Union["):-1]
            parts = [p.strip() for p in inner.split(",") if p.strip() != "None"]
            base = parts[0] if parts else "str"
        elif base.startswith("list[") or base.startswith("List["):
            return "array"
        elif base.startswith("dict[") or base.startswith("Dict["):
            return "object"
        return TYPES_MAP.get(base, "string")

    # Sin `from __future__`, llega el tipo real
    if annotation is type(None):
        return "string"
    if hasattr(annotation, "__origin__"):
        origin = annotation.__origin__
        args = getattr(annotation, "__args__", ())
        non_none = [a for a in args if a is not type(None)]
        if non_none:
            return _py_type_to_json(non_none[0])
        if origin is list:
            return "array"
        if origin is dict:
            return "object"
    return TYPES_MAP.get(getattr(annotation, "__name__", ""), "string")


def _build_schema(func: Callable, name: str, description: str) -> dict:
    """Construye schema Anthropic desde la firma de func."""
    sig = inspect.signature(func)
    properties: dict[str, dict] = {}
    required: list[str] = []

    for pname, param in sig.parameters.items():
        if pname in ("self", "cls"):
            continue
        json_type = _py_type_to_json(param.annotation)
        prop: dict[str, Any] = {"type": json_type}
        if param.default is inspect.Parameter.empty:
            required.append(pname)
        else:
            prop["default"] = param.default
        properties[pname] = prop

    return {
        "name": name,
        "description": description,
        "input_schema": {
            "type": "object",
            "properties": properties,
            "required": required,
        },
    }


def tool(name: Optional[str] = None, description: Optional[str] = None):
    """Decorador que registra una función como tool."""

    def decorator(func: Callable) -> Callable:
        tool_name = name or func.__name__
        if tool_name in TOOL_REGISTRY:
            raise RuntimeError(f"Tool '{tool_name}' ya está registrado")
        desc = description or (func.__doc__ or "").strip().split("\n")[0] or tool_name
        TOOL_REGISTRY[tool_name] = {
            "func": func,
            "schema": _build_schema(func, tool_name, desc),
            "description": desc,
        }
        return func

    return decorator


def list_schemas() -> list[dict]:
    """Devuelve todos los schemas registrados."""
    return [entry["schema"] for entry in TOOL_REGISTRY.values()]


def tool_names() -> list[str]:
    """Lista de nombres registrados."""
    return list(TOOL_REGISTRY.keys())


def execute(name: str, args: dict, timeout: int = 30) -> str:
    """Ejecuta un tool por nombre con timeout. Devuelve siempre str."""
    if name not in TOOL_REGISTRY:
        return f"Error: tool '{name}' no registrado"

    func = TOOL_REGISTRY[name]["func"]
    try:
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(func, **args)
            result = future.result(timeout=timeout)
        return result if isinstance(result, str) else str(result)
    except FutureTimeout:
        return f"Error ejecutando '{name}': timeout de {timeout}s"
    except TypeError as e:
        return f"Error ejecutando '{name}': argumentos inválidos ({e})"
    except Exception as e:
        return f"Error ejecutando '{name}': {type(e).__name__}: {e}"


def clear_registry() -> None:
    """Vacía el registro (útil para tests)."""
    TOOL_REGISTRY.clear()


if __name__ == "__main__":
    @tool(description="Suma dos enteros")
    def add(a: int, b: int) -> int:
        """Suma a + b."""
        return a + b

    @tool(description="Saluda a alguien")
    def greet(name: str, excited: bool = False) -> str:
        """Saluda a name."""
        return f"¡Hola {name}{'!' if excited else '.'}"

    print(tool_names())
    print(json.dumps(list_schemas(), indent=2, ensure_ascii=False))
    print(execute("add", {"a": 2, "b": 3}))
    print(execute("greet", {"name": "Rafael", "excited": True}))
    print(execute("noexiste", {}))
    print("OK registry")
