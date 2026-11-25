import json
import sqlite3
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from kai.storage.database import Database


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Repository:
    def __init__(self, database: Database) -> None:
        self.database = database

    def create_conversation(self) -> str:
        conversation_id = str(uuid4())
        with self.database.connection() as connection:
            connection.execute(
                "INSERT INTO conversations (id, created_at) VALUES (?, ?)",
                (conversation_id, _utc_now()),
            )
        return conversation_id

    def add_message(
        self,
        conversation_id: str,
        role: str,
        content: str,
        tool_calls: list[dict[str, Any]] | None = None,
        tool_name: str | None = None,
    ) -> None:
        with self.database.connection() as connection:
            connection.execute(
                """
                INSERT INTO messages
                    (conversation_id, role, content, tool_calls_json,
                     tool_name, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    conversation_id,
                    role,
                    content,
                    json.dumps(tool_calls) if tool_calls is not None else None,
                    tool_name,
                    _utc_now(),
                ),
            )

    def get_messages(self, conversation_id: str) -> list[dict[str, Any]]:
        with self.database.connection() as connection:
            rows = connection.execute(
                """
                SELECT role, content, tool_calls_json, tool_name
                FROM messages
                WHERE conversation_id = ?
                ORDER BY id
                """,
                (conversation_id,),
            ).fetchall()
        messages = []
        for row in rows:
            message: dict[str, Any] = {
                "role": row["role"],
                "content": row["content"],
            }
            if row["tool_calls_json"]:
                message["tool_calls"] = json.loads(row["tool_calls_json"])
            if row["tool_name"]:
                message["name"] = row["tool_name"]
            messages.append(message)
        return messages

    def save_memory(self, content: str) -> int:
        with self.database.connection() as connection:
            cursor = connection.execute(
                "INSERT INTO memories (content, created_at) VALUES (?, ?)",
                (content, _utc_now()),
            )
            return int(cursor.lastrowid)

    def search_memories(
        self, query: str, limit: int = 5
    ) -> list[dict[str, Any]]:
        if not 1 <= limit <= 10:
            raise ValueError("Memory search limit must be between 1 and 10.")
        with self.database.connection() as connection:
            rows = connection.execute(
                """
                SELECT id, content, created_at
                FROM memories
                WHERE instr(lower(content), lower(?)) > 0
                ORDER BY id DESC
                LIMIT ?
                """,
                (query, limit),
            ).fetchall()
        return [dict(row) for row in rows]
