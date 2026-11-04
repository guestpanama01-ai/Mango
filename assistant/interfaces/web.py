"""Servidor web local (FastAPI) para el asistente."""
from __future__ import annotations

import os
from pathlib import Path
import shutil

from fastapi import FastAPI, File, UploadFile, Request, HTTPException, Depends
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from assistant.config import DATA_DIR
from assistant.core.agent import get_agent
from assistant.core.memory import ShortTermMemory, init_db

import assistant.tools.files  # noqa: F401
import assistant.tools.shell  # noqa: F401
import assistant.tools.web    # noqa: F401
import assistant.tools.memory_tool  # noqa: F401
import assistant.tools.utils  # noqa: F401
import assistant.tools.tasks  # noqa: F401
import assistant.tools.obsidian  # noqa: F401

app = FastAPI(title="Asistente IA Web")

# Permitir peticiones desde GitHub Pages y localhost
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # En producción, cambia "*" por tu URL de GitHub Pages si quieres más seguridad
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.middleware("http")
async def add_no_cache_header(request, call_next):
    response = await call_next(request)
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response

MASTER_KEY = os.getenv("MASTER_KEY", "mango-secreto-123")

def verify_key(request: Request):
    key = request.headers.get("X-Master-Key")
    if key != MASTER_KEY:
        raise HTTPException(status_code=401, detail="Llave incorrecta")

STATIC_DIR = Path(__file__).parent / "static"
init_db()

class ChatRequest(BaseModel):
    message: str
    model: str = "groq"

class ChatResponse(BaseModel):
    reply: str

@app.post("/chat", response_model=ChatResponse, dependencies=[Depends(verify_key)])
async def chat_endpoint(req: ChatRequest):
    agent = get_agent()
    try:
        reply = agent.run(req.message)
        return ChatResponse(reply=reply)
    except Exception as e:
        return ChatResponse(reply=f"Error: {e}")

@app.post("/chat/stream", dependencies=[Depends(verify_key)])
async def chat_stream_endpoint(req: ChatRequest):
    agent = get_agent()
    return StreamingResponse(agent.run_stream(req.message), media_type="text/event-stream")

@app.post("/upload", dependencies=[Depends(verify_key)])
async def upload_file(file: UploadFile = File(...)):
    MAX_SIZE = 10 * 1024 * 1024
    file.file.seek(0, 2)
    if file.file.tell() > MAX_SIZE:
        return {"status": "error", "message": "Archivo mayor a 10MB."}
    file.file.seek(0)

    workspace = DATA_DIR / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)
    safe_filename = Path(file.filename).name
    file_path = workspace / safe_filename
    try:
        with file_path.open("wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        return {"filename": safe_filename, "status": "ok"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.get("/history", dependencies=[Depends(verify_key)])
async def get_history():
    return {"messages": ShortTermMemory().get_context(limit=50)}

@app.post("/clear", dependencies=[Depends(verify_key)])
async def clear_history():
    ShortTermMemory().clear()
    return {"status": "ok"}

# Rutas estáticas
@app.get("/")
async def serve_index():
    return FileResponse(STATIC_DIR / "index.html")

@app.get("/style.css")
async def serve_css():
    return FileResponse(STATIC_DIR / "style.css")

@app.get("/app.js")
async def serve_js():
    return FileResponse(STATIC_DIR / "app.js")

@app.get("/manifest.json")
async def serve_manifest():
    return FileResponse(STATIC_DIR / "manifest.json")

@app.get("/sw.js")
async def serve_sw():
    return FileResponse(STATIC_DIR / "sw.js")

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)