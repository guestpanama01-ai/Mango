"""Registro de tools con schema JSON autogenerado."""
from __future__ import annotations

import inspect
import multiprocessing
from typing import Any, Callable, Optional

TYPES_MAP: dict[str, str] = {
    "str": "string", "int": "integer", "float": "number",
    "bool": "boolean", "list": "array", "dict": "object",
}

TOOL_REGISTRY: dict[str, dict] = {}

def _py_type_to_json(annotation: Any) -> str:
    if annotation is inspect.Parameter.empty:
        return "string"
    if isinstance(annotation, str):
        base = annotation
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
    if annotation is type(None):
        return "string"
    if hasattr(annotation, "__origin__"):
        origin = annotation.__origin__
        args = getattr(annotation, "__args__", ())
        non_none = [a for a in args if a is not type(None)]
        if non_none:
            return _py_type_to_json(non_none[0])
        if origin is list: return "array"
        if origin is dict: return "object"
    return TYPES_MAP.get(getattr(annotation, "__name__", ""), "string")

def _build_schema(func: Callable, name: str, description: str) -> dict:
    sig = inspect.signature(func)
    properties: dict[str, dict] = {}
    required: list[str] = []
    for pname, param in sig.parameters.items():
        if pname in ("self", "cls"): continue
        json_type = _py_type_to_json(param.annotation)
        prop: dict[str, Any] = {"type": json_type}
        if param.default is inspect.Parameter.empty:
            required.append(pname)
        else:
            prop["default"] = param.default
        properties[pname] = prop
    return {
        "name": name, "description": description,
        "input_schema": {"type": "object", "properties": properties, "required": required},
    }

def tool(name: Optional[str] = None, description: Optional[str] = None):
    def decorator(func: Callable) -> Callable:
        tool_name = name or func.__name__
        if tool_name in TOOL_REGISTRY:
            raise RuntimeError(f"Tool '{tool_name}' ya está registrado")
        desc = description or (func.__doc__ or "").strip().split("\n")[0] or tool_name
        TOOL_REGISTRY[tool_name] = {
            "func": func, "schema": _build_schema(func, tool_name, desc), "description": desc,
        }
        return func
    return decorator

def list_schemas() -> list[dict]:
    return [entry["schema"] for entry in TOOL_REGISTRY.values()]

def tool_names() -> list[str]:
    return list(TOOL_REGISTRY.keys())

def _run_in_process(func: Callable, args: dict, result_queue: multiprocessing.Queue):
    try:
        result = func(**args)
        result_queue.put(str(result) if not isinstance(result, str) else result)
    except Exception as e:
        result_queue.put(f"Error: {type(e).__name__}: {e}")

def execute(name: str, args: dict, timeout: int = 30) -> str:
    if name not in TOOL_REGISTRY:
        return f"Error: tool '{name}' no registrado"
    
    func = TOOL_REGISTRY[name]["func"]
    result_queue = multiprocessing.Queue()
    process = multiprocessing.Process(target=_run_in_process, args=(func, args, result_queue))
    
    process.start()
    process.join(timeout)
    
    if process.is_alive():
        process.terminate()
        process.join()
        return f"Error ejecutando '{name}': timeout de {timeout}s"
    
    return result_queue.get() if not result_queue.empty() else "Error: sin resultado"

def clear_registry() -> None:
    TOOL_REGISTRY.clear()