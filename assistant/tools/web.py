"""Servidor web local (FastAPI) para el asistente."""
from __future__ import annotations

import os
from pathlib import Path
import shutil

from fastapi import FastAPI, File, UploadFile, Request, HTTPException, Depends
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from assistant.config import DATA_DIR

from assistant.core.memory import ShortTermMemory, init_db

import assistant.tools.files  # noqa: F401
import assistant.tools.shell  # noqa: F401
import assistant.tools.web    # noqa: F401
import assistant.tools.memory_tool  # noqa: F401
import assistant.tools.utils  # noqa: F401
import assistant.tools.tasks  # noqa: F401

app = FastAPI(title="Asistente IA Web")

# --- SEGURIDAD: CORS (Solo acepta tu navegador local) ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8000", "http://127.0.0.1:8000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- SEGURIDAD: Middleware de caché ---
@app.middleware("http")
async def add_no_cache_header(request, call_next):
    response = await call_next(request)
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response

# --- SEGURIDAD: Llave de acceso ---
MASTER_KEY = os.getenv("MASTER_KEY", "mango-secreto-123")

def verify_key(request: Request):
    """Verifica que la petición incluya la llave secreta."""
    # En el navegador, la llave se enviará en la cookie o en el header
    key = request.headers.get("X-Master-Key") or request.cookies.get("master_key")
    if key != MASTER_KEY:
        raise HTTPException(status_code=401, detail="Llave de acceso incorrecta")
    return True

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
        return ChatResponse(reply=f"Error interno: {type(e).__name__}: {e}")

@app.post("/chat/stream", dependencies=[Depends(verify_key)])
async def chat_stream_endpoint(req: ChatRequest):
    agent = get_agent()
    return StreamingResponse(agent.run_stream(req.message), media_type="text/event-stream")

@app.post("/upload", dependencies=[Depends(verify_key)])
async def upload_file(file: UploadFile = File(...)):
    # SEGURIDAD: Limitar el tamaño del archivo a 10 MB
    MAX_SIZE = 10 * 1024 * 1024
    file.file.seek(0, 2)
    size = file.file.tell()
    file.file.seek(0)
    if size > MAX_SIZE:
        return {"status": "error", "message": "El archivo supera el límite de 10 MB."}

    workspace = DATA_DIR / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)
    safe_filename = Path(file.filename).name
    file_path = workspace / safe_filename
    try:
        with file_path.open("wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        return {"filename": safe_filename, "status": "ok", "message": f"Archivo guardado como '{safe_filename}'."}
    except Exception as e:
        return {"status": "error", "message": f"No se pudo guardar: {e}"}

@app.get("/history", dependencies=[Depends(verify_key)])
async def get_history():
    stm = ShortTermMemory()
    return {"messages": stm.get_context(limit=50)}

@app.post("/clear", dependencies=[Depends(verify_key)])
async def clear_history():
    stm = ShortTermMemory()
    stm.clear()
    return {"status": "ok"}

# Servir archivos estáticos (sin protección para que cargue el HTML)
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