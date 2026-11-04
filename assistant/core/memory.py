"""Memoria corta y larga del asistente, persistida en SQLite/Turso."""
from __future__ import annotations

import os
import sqlite3
from datetime import datetime, date
from typing import Optional

from assistant.config import DB_PATH, MAX_CONTEXT_TOKENS

try:
    import libsql
    HAS_TURSO = True
except ImportError:
    HAS_TURSO = False

def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")

def _connect():
    url = os.getenv("TURSO_DATABASE_URL")
    token = os.getenv("TURSO_AUTH_TOKEN")
    
    if HAS_TURSO and url and token:
        return libsql.connect(database=url, auth_token=token)
    
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA busy_timeout=5000;")
    return conn

def init_db() -> None:
    with _connect() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                tokens INTEGER DEFAULT 0,
                ts TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS facts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                key TEXT UNIQUE NOT NULL,
                value TEXT NOT NULL,
                ts TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS usage (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                provider TEXT NOT NULL,
                model TEXT NOT NULL,
                tokens INTEGER NOT NULL,
                ts TEXT NOT NULL
            );
        """)
        
        # Intentamos crear la tabla FTS y sus triggers (si no existen)
        try:
            conn.execute("""
                CREATE VIRTUAL TABLE IF NOT EXISTS facts_fts USING fts5(
                    key, value, content='facts', content_rowid='id'
                );
            """)
            # Al usar 'INSERT OR REPLACE' en SQLite, el trigger de DELETE no se dispara a veces.
            # Para solucionarlo, usamos 'rebuild' al iniciar para asegurar que todo esté indexado.
            conn.executescript("""
                CREATE TRIGGER IF NOT EXISTS facts_ai AFTER INSERT ON facts BEGIN
                    INSERT INTO facts_fts(rowid, key, value) VALUES (new.id, new.key, new.value);
                END;
                CREATE TRIGGER IF NOT EXISTS facts_ad AFTER DELETE ON facts BEGIN
                    INSERT INTO facts_fts(facts_fts, rowid, key, value) VALUES('delete', old.id, old.key, old.value);
                END;
                CREATE TRIGGER IF NOT EXISTS facts_au AFTER UPDATE ON facts BEGIN
                    INSERT INTO facts_fts(facts_fts, rowid, key, value) VALUES('delete', old.id, old.key, old.value);
                    INSERT INTO facts_fts(rowid, key, value) VALUES (new.id, new.key, new.value);
                END;
            """)
            # Forzamos la reconstrucción del índice al iniciar
            conn.execute("INSERT INTO facts_fts(facts_fts) VALUES('rebuild');")
        except Exception:
            pass

def estimate_tokens(text: str) -> int:
    return len(text) // 4

class ShortTermMemory:
    def add(self, role: str, content: str, tokens: int = 0) -> None:
        with _connect() as conn:
            conn.execute(
                "INSERT INTO messages (role, content, tokens, ts) VALUES (?, ?, ?, ?)",
                (role, content, tokens or estimate_tokens(content), _now()),
            )

    def get_context(self, limit: int = 20) -> list[dict]:
        with _connect() as conn:
            rows = conn.execute(
                "SELECT role, content FROM messages ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
        return [{"role": r[0], "content": r[1]} for r in reversed(rows)]

    def clear(self) -> None:
        with _connect() as conn:
            conn.execute("DELETE FROM messages")

class LongTermMemory:
    def set_fact(self, key: str, value: str) -> None:
        with _connect() as conn:
            # Borramos primero para asegurar que el trigger de delete se dispare y limpie el FTS
            conn.execute("DELETE FROM facts WHERE key = ?", (key,))
            conn.execute(
                "INSERT INTO facts (key, value, ts) VALUES (?, ?, ?)",
                (key, value, _now()),
            )

    def get_fact(self, key: str) -> Optional[str]:
        with _connect() as conn:
            row = conn.execute("SELECT value FROM facts WHERE key = ?", (key,)).fetchone()
        return row[0] if row else None

    def all_facts(self) -> dict[str, str]:
        with _connect() as conn:
            rows = conn.execute("SELECT key, value FROM facts").fetchall()
        return {r[0]: r[1] for r in rows}

    def search_facts(self, query: str, limit: int = 5) -> dict[str, str]:
        """Busca hechos relevantes usando FTS5 con lógica OR."""
        # Limpiamos la query
        words = "".join(c for c in query if c.isalnum() or c.isspace()).split()
        if not words:
            return {}
        
        # Unimos las palabras con OR para que busque cualquiera de ellas
        safe_query = " OR ".join(words) + "*"
        
        with _connect() as conn:
            try:
                rows = conn.execute(
                    "SELECT key, value FROM facts_fts WHERE facts_fts MATCH ? LIMIT ?",
                    (safe_query, limit)
                ).fetchall()
                if rows:
                    return {r[0]: r[1] for r in rows}
            except Exception:
                pass
            
            # Fallback: Si no hay resultados o falla, devolvemos los últimos 5
            rows = conn.execute("SELECT key, value FROM facts LIMIT 5").fetchall()
            return {r[0]: r[1] for r in rows}

    def delete_fact(self, key: str) -> bool:
        with _connect() as conn:
            cur = conn.execute("DELETE FROM facts WHERE key = ?", (key,))
        return cur.rowcount > 0

class TokenCounter:
    def log(self, provider: str, model: str, tokens: int) -> None:
        with _connect() as conn:
            conn.execute(
                "INSERT INTO usage (provider, model, tokens, ts) VALUES (?, ?, ?, ?)",
                (provider, model, tokens, _now()),
            )

    def daily_total(self, day: Optional[str] = None) -> int:
        day = day or date.today().isoformat()
        with _connect() as conn:
            row = conn.execute(
                "SELECT COALESCE(SUM(tokens), 0) FROM usage WHERE ts LIKE ?", (f"{day}%",)
            ).fetchone()
        return int(row[0])

    def by_provider(self, day: Optional[str] = None) -> dict[str, int]:
        day = day or date.today().isoformat()
        with _connect() as conn:
            rows = conn.execute(
                "SELECT provider, SUM(tokens) FROM usage WHERE ts LIKE ? GROUP BY provider",
                (f"{day}%",),
            ).fetchall()
        return {r[0]: int(r[1]) for r in rows}

def build_context(system_prompt, facts, history, max_tokens=MAX_CONTEXT_TOKENS):
    facts_str = "\n".join(f"- {k}: {v}" for k, v in facts.items()) or "(sin hechos)"
    system_content = f"{system_prompt}\n\nHechos conocidos:\n{facts_str}"
    kept = []
    total = estimate_tokens(system_content)
    for msg in reversed(history):
        cost = estimate_tokens(msg["content"])
        if total + cost > max_tokens: break
        kept.append(msg)
        total += cost
    kept.reverse()
    return [{"role": "system", "content": system_content}, *kept]