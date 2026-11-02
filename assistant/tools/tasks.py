"""Herramientas para gestionar notas y recordatorios."""
from __future__ import annotations
import sqlite3
from datetime import datetime
from assistant.config import DB_PATH
from assistant.tools.registry import tool

def _connect():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_tasks_db():
    with _connect() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                description TEXT NOT NULL,
                created_at TEXT NOT NULL,
                done INTEGER DEFAULT 0
            )
        """)

@tool(description="Añade una nota o recordatorio a la lista de tareas del usuario.")
def add_task(description: str) -> str:
    init_tasks_db()
    with _connect() as conn:
        conn.execute(
            "INSERT INTO tasks (description, created_at) VALUES (?, ?)",
            (description, datetime.now().isoformat())
        )
    return f"OK: Tarea guardada: '{description}'"

@tool(description="Lista todas las notas o recordatorios pendientes del usuario.")
def list_tasks() -> str:
    init_tasks_db()
    with _connect() as conn:
        rows = conn.execute("SELECT id, description FROM tasks WHERE done = 0 ORDER BY id DESC").fetchall()
    if not rows:
        return "No tienes tareas pendientes."
    return "\n".join(f"[{r['id']}] {r['description']}" for r in rows)

@tool(description="Marca una tarea como completada usando su ID numérico.")
def complete_task(task_id: int) -> str:
    init_tasks_db()
    with _connect() as conn:
        cur = conn.execute("UPDATE tasks SET done = 1 WHERE id = ?", (task_id,))
    if cur.rowcount > 0:
        return f"OK: Tarea {task_id} completada."
    return f"Error: No se encontró la tarea con ID {task_id}."