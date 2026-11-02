"""Servidor web local (FastAPI) para el asistente."""
from __future__ import annotations

from pathlib import Path
from fastapi import FastAPI
from fastapi.responses import FileResponse
from pydantic import BaseModel

from assistant.core.agent import get_agent
from assistant.core.memory import ShortTermMemory, init_db
import assistant.tools.files  # noqa: F401
import assistant.tools.shell  # noqa: F401
import assistant.tools.web    # noqa: F401

app = FastAPI(title="Asistente IA Web")

# Evitar que el navegador guarde los archivos en caché
@app.middleware("http")
async def add_no_cache_header(request, call_next):
    response = await call_next(request)
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response

STATIC_DIR = Path(__file__).parent / "static"
init_db()

class ChatRequest(BaseModel):
    message: str
    model: str = "groq"

class ChatResponse(BaseModel):
    reply: str

@app.post("/chat", response_model=ChatResponse)
async def chat_endpoint(req: ChatRequest):
    agent = get_agent()
    try:
        reply = agent.run(req.message)
        return ChatResponse(reply=reply)
    except Exception as e:
        return ChatResponse(reply=f"Error interno: {type(e).__name__}: {e}")

@app.get("/history")
async def get_history():
    stm = ShortTermMemory()
    messages = stm.get_context(limit=50)
    return {"messages": messages}

@app.post("/clear")
async def clear_history():
    stm = ShortTermMemory()
    stm.clear()
    return {"status": "ok"}

@app.get("/")
async def serve_index():
    return FileResponse(STATIC_DIR / "index.html")

@app.get("/style.css")
async def serve_css():
    return FileResponse(STATIC_DIR / "style.css")

@app.get("/app.js")
async def serve_js():
    return FileResponse(STATIC_DIR / "app.js")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)
    import assistant.tools.files  # noqa: F401
import assistant.tools.shell  # noqa: F401
import assistant.tools.web    # noqa: F401  # <--- AÑADE ESTA LÍNEA
import assistant.tools.utils