"""Herramientas para leer y buscar en tu bóveda de Obsidian."""
from __future__ import annotations

import os
import urllib.request
import urllib.error
import json
from assistant.tools.registry import tool

OBSIDIAN_PORT = os.getenv("OBSIDIAN_PORT", "27123")
OBSIDIAN_API_KEY = os.getenv("OBSIDIAN_API_KEY", "")
BASE_URL = f"http://127.0.0.1:{OBSIDIAN_PORT}"

def _make_request(endpoint: str, method: str = "GET", data: dict = None) -> dict | str:
    """Hace una petición a la API local de Obsidian."""
    url = f"{BASE_URL}{endpoint}"
    headers = {
        "Authorization": f"Bearer {OBSIDIAN_API_KEY}",
        "Content-Type": "application/json"
    }
    
    req = urllib.request.Request(url, method=method, headers=headers)
    if data:
        req.data = json.dumps(data).encode("utf-8")
        
    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            body = response.read().decode("utf-8")
            if not body:
                return {}
            return json.loads(body)
    except urllib.error.HTTPError as e:
        return {"error": f"Error HTTP {e.code}: {e.reason}"}
    except urllib.error.URLError as e:
        return {"error": f"No se pudo conectar a Obsidian. ¿Está abierto? ({e.reason})"}
    except json.JSONDecodeError:
        return {"error": "El plugin devolvió un formato que no es JSON. Revisa la versión del plugin."}
    except Exception as e:
        return {"error": f"Error: {type(e).__name__}: {e}"}

@tool(description="Busca notas en tu bóveda de Obsidian usando palabras clave.")
def obsidian_search(query: str) -> str:
    """Busca en tus notas de Obsidian."""
    # El endpoint correcto del plugin para búsqueda es POST /search/ con un JSON
    payload = {"query": query}
    result = _make_request("/search/", method="POST", data=payload)
    
    if isinstance(result, dict) and "error" in result:
        return result["error"]
        
    if not result or not isinstance(result, list):
        return f"No encontré notas sobre '{query}'."
        
    output = f"Resultados para '{query}':\n"
    for match in result[:5]: # Mostramos solo los 5 primeros
        filename = match.get("filename", "Desconocido")
        content = match.get("content", "")[:200] 
        output += f"- **{filename}**: {content}...\n"
    return output

@tool(description="Lee el contenido completo de una nota específica de Obsidian.")
def obsidian_read_note(filename: str) -> str:
    """Lee una nota de Obsidian por su nombre o ruta (ej. 'Mi Nota.md')."""
    if not filename.endswith(".md"):
        filename += ".md"
        
    result = _make_request(f"/vault/{filename}")
    
    if isinstance(result, dict) and "error" in result:
        return result["error"]
    
    return result if isinstance(result, str) else "No se pudo leer el contenido."