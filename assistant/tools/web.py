"""Tools web: HTTP GET y búsqueda con ddgs (sin API key)."""
from __future__ import annotations

import json
import urllib.error
import urllib.request

from assistant.tools.registry import tool

USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) AsistentePersonal/0.1"
HTTP_TIMEOUT = 15
MAX_BODY_CHARS = 20_000


def _http_get(url: str, accept: str = "*/*") -> tuple[int, str, str]:
    """GET simple. Devuelve (status, content_type, body)."""
    req = urllib.request.Request(url, headers={
        "User-Agent": USER_AGENT,
        "Accept": accept,
    })
    with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as resp:
        content_type = resp.headers.get("Content-Type", "")
        raw = resp.read()
        try:
            body = raw.decode("utf-8", errors="replace")
        except Exception:
            body = raw.decode("latin-1", errors="replace")
        return resp.status, content_type, body


@tool(description="Descarga una URL y devuelve el contenido (texto o HTML truncado)")
def http_get(url: str) -> str:
    """GET de una URL. Devuelve status + content-type + body."""
    if not url.startswith(("http://", "https://")):
        return "Error: la URL debe empezar con http:// o https://"

    try:
        status, content_type, body = _http_get(url)
    except urllib.error.HTTPError as e:
        return f"Error HTTP {e.code}: {e.reason}"
    except urllib.error.URLError as e:
        return f"Error de red: {e.reason}"
    except TimeoutError:
        return f"Error: timeout de {HTTP_TIMEOUT}s"
    except Exception as e:
        return f"Error: {type(e).__name__}: {e}"

    if len(body) > MAX_BODY_CHARS:
        body = body[:MAX_BODY_CHARS] + f"\n... (truncado, {len(body)} chars totales)"

    return f"[status {status}] [content-type {content_type}]\n{body}"


@tool(description="Busca en la web y devuelve los primeros resultados (título, URL, snippet)")
def web_search(query: str, max_results: int = 5) -> str:
    """Busca usando la librería ddgs (metasearch, sin API key)."""
    if not query.strip():
        return "Error: query vacía"

    max_results = max(1, min(int(max_results), 10))

    try:
        from ddgs import DDGS
    except ImportError:
        return "Error: falta instalar la librería. Ejecuta: pip install ddgs"

    try:
        with DDGS() as ddgs:
            raw = list(ddgs.text(query, max_results=max_results))
    except Exception as e:
        return f"Error en búsqueda: {type(e).__name__}: {e}"

    if not raw:
        return "(sin resultados)"

    results = [
        {
            "title": r.get("title", ""),
            "url": r.get("href", "") or r.get("url", ""),
            "snippet": r.get("body", ""),
        }
        for r in raw
    ]
    return json.dumps(results, indent=2, ensure_ascii=False)


if __name__ == "__main__":
    print("--- http_get ---")
    print(http_get("https://example.com")[:300])
    print("\n--- http_get URL inválida ---")
    print(http_get("ftp://algo"))
    print("\n--- web_search ---")
    print(web_search("python asyncio tutorial", max_results=3))
    print("\nOK web")
