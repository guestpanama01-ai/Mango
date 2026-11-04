"""Memoria corta y larga del asistente, persistida en SQLite."""
from __future__ import annotations

import sqlite3
from datetime import datetime, date
from typing import Optional

from assistant.config import DB_PATH, MAX_CONTEXT_TOKENS


def _now() -> str:
    """Timestamp ISO actual."""
    return datetime.now().isoformat(timespec="seconds")


def _connect() -> sqlite3.Connection:
    """Abre conexión a la DB con row_factory."""
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    """Crea tablas e índices si no existen."""
    with _connect() as conn:
        conn.executescript(
            """
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
            CREATE INDEX IF NOT EXISTS idx_messages_ts ON messages(ts);
            CREATE INDEX IF NOT EXISTS idx_usage_ts ON usage(ts);
            """
        )
        # Creamos la tabla virtual FTS5 para búsqueda rápida de hechos
        # Si ya existe, lanzará un error de "ya existe", lo ignoramos.
        try:
            conn.execute("""
                CREATE VIRTUAL TABLE IF NOT EXISTS facts_fts USING fts5(
                    key, value, content='facts', content_rowid='id'
                );
            """)
            # Triggers para mantener el índice FTS5 sincronizado con la tabla 'facts'
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
        except sqlite3.OperationalError:
            pass # Si ya existen los triggers, no hacemos nada


def estimate_tokens(text: str) -> int:
    """Aproximación burda: 1 token ≈ 4 caracteres."""
    return len(text) // 4


class ShortTermMemory:
    """Historial reciente de mensajes."""

    def add(self, role: str, content: str, tokens: int = 0) -> None:
        """Guarda un mensaje."""
        with _connect() as conn:
            conn.execute(
                "INSERT INTO messages (role, content, tokens, ts) VALUES (?, ?, ?, ?)",
                (role, content, tokens or estimate_tokens(content), _now()),
            )

    def get_context(self, limit: int = 20) -> list[dict]:
        """Devuelve los últimos `limit` mensajes en orden cronológico."""
        with _connect() as conn:
            rows = conn.execute(
                "SELECT role, content FROM messages ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [{"role": r["role"], "content": r["content"]} for r in reversed(rows)]

    def clear(self) -> None:
        """Borra todo el historial."""
        with _connect() as conn:
            conn.execute("DELETE FROM messages")


class LongTermMemory:
    """Hechos persistentes sobre el usuario/proyecto."""

    def set_fact(self, key: str, value: str) -> None:
        """Crea o actualiza un hecho."""
        with _connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO facts (key, value, ts) VALUES (?, ?, ?)",
                (key, value, _now()),
            )

    def get_fact(self, key: str) -> Optional[str]:
        """Devuelve el valor o None."""
        with _connect() as conn:
            row = conn.execute(
                "SELECT value FROM facts WHERE key = ?", (key,)
            ).fetchone()
        return row["value"] if row else None

    def all_facts(self) -> dict[str, str]:
        """Todos los hechos como dict."""
        with _connect() as conn:
            rows = conn.execute("SELECT key, value FROM facts").fetchall()
        return {r["key"]: r["value"] for r in rows}

    def search_facts(self, query: str, limit: int = 5) -> dict[str, str]:
        """Busca hechos relevantes usando FTS5."""
        # Limpiamos la query para evitar errores de sintaxis en FTS5
        safe_query = "".join(c for c in query if c.isalnum() or c.isspace())
        if not safe_query.strip():
            return {}
        
        with _connect() as conn:
            try:
                # Buscamos en la tabla virtual
                rows = conn.execute(
                    "SELECT key, value FROM facts_fts WHERE facts_fts MATCH ? LIMIT ?",
                    (safe_query, limit)
                ).fetchall()
                return {r["key"]: r["value"] for r in rows}
            except sqlite3.OperationalError:
                # Si FTS falla (por sintaxis), devolvemos los últimos 5 por seguridad
                rows = conn.execute("SELECT key, value FROM facts LIMIT 5").fetchall()
                return {r["key"]: r["value"] for r in rows}

    def delete_fact(self, key: str) -> bool:
        """Borra un hecho. True si existía."""
        with _connect() as conn:
            cur = conn.execute("DELETE FROM facts WHERE key = ?", (key,))
        return cur.rowcount > 0


class TokenCounter:
    """Registro de consumo de tokens por proveedor."""

    def log(self, provider: str, model: str, tokens: int) -> None:
        """Registra uso."""
        with _connect() as conn:
            conn.execute(
                "INSERT INTO usage (provider, model, tokens, ts) VALUES (?, ?, ?, ?)",
                (provider, model, tokens, _now()),
            )

    def daily_total(self, day: Optional[str] = None) -> int:
        """Total de tokens en un día (YYYY-MM-DD, default hoy)."""
        day = day or date.today().isoformat()
        with _connect() as conn:
            row = conn.execute(
                "SELECT COALESCE(SUM(tokens), 0) AS total FROM usage WHERE ts LIKE ?",
                (f"{day}%",),
            ).fetchone()
        return int(row["total"])

    def by_provider(self, day: Optional[str] = None) -> dict[str, int]:
        """Total por proveedor en un día."""
        day = day or date.today().isoformat()
        with _connect() as conn:
            rows = conn.execute(
                "SELECT provider, SUM(tokens) AS total FROM usage "
                "WHERE ts LIKE ? GROUP BY provider",
                (f"{day}%",),
            ).fetchall()
        return {r["provider"]: int(r["total"]) for r in rows}


def build_context(
    system_prompt: str,
    facts: dict[str, str],
    history: list[dict],
    max_tokens: int = MAX_CONTEXT_TOKENS,
) -> list[dict]:
    """Arma la lista de mensajes para el LLM, recortando si excede max_tokens."""
    facts_str = "\n".join(f"- {k}: {v}" for k, v in facts.items()) or "(sin hechos)"
    system_content = f"{system_prompt}\n\nHechos conocidos:\n{facts_str}"

    kept: list[dict] = []
    total = estimate_tokens(system_content)
    for msg in reversed(history):
        cost = estimate_tokens(msg["content"])
        if total + cost > max_tokens:
            break
        kept.append(msg)
        total += cost
    kept.reverse()

    return [{"role": "system", "content": system_content}, *kept]