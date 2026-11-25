import json
import re
import sqlite3
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from kai.storage.database import Database

MEMORY_CATEGORIES = {
    "user_preference",
    "personal_profile",
    "education_work",
    "project",
    "workflow",
    "explicit_fact",
}

_STOP_WORDS = {
    "about", "after", "again", "also", "and", "are", "can", "could",
    "did", "does", "for", "from", "have", "help", "how", "into", "just",
    "know", "me", "my", "our", "please", "remember", "show", "tell",
    "that", "the", "their", "them", "then", "there", "these", "this",
    "those", "what", "when", "where", "which", "who", "why", "with",
    "would", "you", "your",
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize_content(content: str) -> str:
    return " ".join(content.casefold().split())


def _search_terms(query: str) -> list[str]:
    words = re.findall(r"[^\W_]{2,}", query.casefold(), flags=re.UNICODE)
    return list(dict.fromkeys(word for word in words if word not in _STOP_WORDS))[
        :8
    ]


def _fts_query(terms: list[str]) -> str:
    return " OR ".join(f'"{term}"*' for term in terms)


class Repository:
    def __init__(self, database: Database) -> None:
        self.database = database

    def create_conversation(self, title: str = "") -> str:
        title = title.strip()[:120]
        conversation_id = str(uuid4())
        now = _utc_now()
        with self.database.connection() as connection:
            connection.execute(
                """
                INSERT INTO conversations (id, title, created_at, updated_at)
                VALUES (?, ?, ?, ?)
                """,
                (conversation_id, title, now, now),
            )
        return conversation_id

    def get_conversation(self, conversation_id: str) -> dict[str, Any] | None:
        with self.database.connection() as connection:
            row = connection.execute(
                """
                SELECT id, title, created_at, updated_at, archived_at
                FROM conversations WHERE id = ?
                """,
                (conversation_id,),
            ).fetchone()
        return dict(row) if row else None

    def list_conversations(
        self, limit: int = 20, include_archived: bool = False
    ) -> list[dict[str, Any]]:
        if not 1 <= limit <= 100:
            raise ValueError("Conversation limit must be between 1 and 100.")
        archived_clause = "" if include_archived else "WHERE archived_at IS NULL"
        with self.database.connection() as connection:
            rows = connection.execute(
                f"""
                SELECT c.id, c.title, c.created_at, c.updated_at, c.archived_at,
                       (SELECT COUNT(*) FROM messages m
                        WHERE m.conversation_id = c.id) AS message_count
                FROM conversations c
                {archived_clause}
                ORDER BY c.updated_at DESC, c.id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [dict(row) for row in rows]

    def set_conversation_title(self, conversation_id: str, title: str) -> None:
        title = title.strip()
        if not title or len(title) > 120:
            raise ValueError("Conversation title must contain 1 to 120 characters.")
        with self.database.connection() as connection:
            cursor = connection.execute(
                """
                UPDATE conversations SET title = ?, updated_at = ?
                WHERE id = ?
                """,
                (title, _utc_now(), conversation_id),
            )
            if cursor.rowcount == 0:
                raise KeyError(f"Conversation '{conversation_id}' was not found.")

    def archive_conversation(self, conversation_id: str) -> None:
        with self.database.connection() as connection:
            cursor = connection.execute(
                """
                UPDATE conversations
                SET archived_at = ?, updated_at = ?
                WHERE id = ? AND archived_at IS NULL
                """,
                (_utc_now(), _utc_now(), conversation_id),
            )
            if cursor.rowcount == 0:
                exists = connection.execute(
                    "SELECT 1 FROM conversations WHERE id = ?",
                    (conversation_id,),
                ).fetchone()
                if exists is None:
                    raise KeyError(f"Conversation '{conversation_id}' was not found.")

    def add_message(
        self,
        conversation_id: str,
        role: str,
        content: str,
        tool_calls: list[dict[str, Any]] | None = None,
        tool_name: str | None = None,
        tool_call_id: str | None = None,
        memory_ids: list[str] | None = None,
    ) -> None:
        now = _utc_now()
        with self.database.connection() as connection:
            row = connection.execute(
                """
                SELECT title, archived_at FROM conversations WHERE id = ?
                """,
                (conversation_id,),
            ).fetchone()
            if row is None:
                raise KeyError(f"Conversation '{conversation_id}' was not found.")
            if row["archived_at"] is not None:
                raise ValueError("Cannot add messages to an archived conversation.")
            title = row["title"]
            if role == "user" and not title:
                title = " ".join(content.split())[:80]
            connection.execute(
                """
                INSERT INTO messages
                    (conversation_id, role, content, tool_calls_json,
                     tool_name, tool_call_id, memory_ids_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    conversation_id,
                    role,
                    content,
                    json.dumps(tool_calls) if tool_calls is not None else None,
                    tool_name,
                    tool_call_id,
                    json.dumps(memory_ids) if memory_ids is not None else None,
                    now,
                ),
            )
            connection.execute(
                """
                UPDATE conversations SET title = ?, updated_at = ? WHERE id = ?
                """,
                (title, now, conversation_id),
            )

    def get_messages(self, conversation_id: str) -> list[dict[str, Any]]:
        with self.database.connection() as connection:
            rows = connection.execute(
                """
                SELECT role, content, tool_calls_json, tool_name,
                       tool_call_id, memory_ids_json, created_at
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
                "created_at": row["created_at"],
            }
            if row["tool_calls_json"]:
                message["tool_calls"] = json.loads(row["tool_calls_json"])
            if row["tool_name"]:
                message["name"] = row["tool_name"]
            if row["tool_call_id"]:
                message["tool_call_id"] = row["tool_call_id"]
            if row["memory_ids_json"]:
                message["memory_ids"] = json.loads(row["memory_ids_json"])
            messages.append(message)
        return messages

    def get_last_assistant_memory_ids(
        self, conversation_id: str
    ) -> list[str]:
        with self.database.connection() as connection:
            row = connection.execute(
                """
                SELECT memory_ids_json FROM messages
                WHERE conversation_id = ? AND role = 'assistant'
                ORDER BY id DESC LIMIT 1
                """,
                (conversation_id,),
            ).fetchone()
        if row is None or not row["memory_ids_json"]:
            return []
        return json.loads(row["memory_ids_json"])

    def create_memory(
        self,
        content: str,
        category: str = "explicit_fact",
        tags: list[str] | None = None,
        source: str = "",
    ) -> dict[str, Any]:
        content = content.strip()
        if not content or len(content) > 2000:
            raise ValueError("Memory content must contain 1 to 2000 characters.")
        if category not in MEMORY_CATEGORIES:
            raise ValueError(f"Unsupported memory category '{category}'.")
        clean_tags = list(dict.fromkeys(tag.strip() for tag in (tags or []) if tag.strip()))[
            :10
        ]
        if any(len(tag) > 50 for tag in clean_tags):
            raise ValueError("Memory tags must not exceed 50 characters.")
        if len(source.strip()) > 500:
            raise ValueError("Memory source must not exceed 500 characters.")
        now = _utc_now()
        normalized = _normalize_content(content)
        memory_id = str(uuid4())
        with self.database.connection() as connection:
            existing = connection.execute(
                """
                SELECT * FROM memories
                WHERE category = ? AND normalized_content = ?
                """,
                (category, normalized),
            ).fetchone()
            if existing:
                result = self._memory_dict(existing)
                result["duplicate"] = True
                return result
            connection.execute(
                """
                INSERT INTO memories
                    (id, category, content, normalized_content, created_at,
                     updated_at, tags_json, source)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    memory_id,
                    category,
                    content,
                    normalized,
                    now,
                    now,
                    json.dumps(clean_tags),
                    source.strip()[:500],
                ),
            )
            row = connection.execute(
                "SELECT * FROM memories WHERE id = ?", (memory_id,)
            ).fetchone()
        return self._memory_dict(row)

    def save_memory(
        self,
        content: str,
        category: str = "explicit_fact",
        tags: list[str] | None = None,
        source: str = "",
    ) -> dict[str, Any]:
        return self.create_memory(content, category, tags, source)

    @staticmethod
    def _memory_dict(row: sqlite3.Row) -> dict[str, Any]:
        result = dict(row)
        result["tags"] = json.loads(result.pop("tags_json"))
        result.pop("normalized_content")
        return result

    def get_memory(self, memory_id: str) -> dict[str, Any] | None:
        with self.database.connection() as connection:
            row = connection.execute(
                "SELECT * FROM memories WHERE id = ?", (memory_id,)
            ).fetchone()
        return self._memory_dict(row) if row else None

    def list_memories(self, limit: int = 50) -> list[dict[str, Any]]:
        if not 1 <= limit <= 100:
            raise ValueError("Memory limit must be between 1 and 100.")
        with self.database.connection() as connection:
            rows = connection.execute(
                "SELECT * FROM memories ORDER BY updated_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [self._memory_dict(row) for row in rows]

    def update_memory(
        self,
        memory_id: str,
        content: str | None = None,
        category: str | None = None,
        tags: list[str] | None = None,
        source: str | None = None,
    ) -> dict[str, Any]:
        current = self.get_memory(memory_id)
        if current is None:
            raise KeyError(f"Memory '{memory_id}' was not found.")
        new_content = (content if content is not None else current["content"]).strip()
        new_category = category or current["category"]
        if not new_content or len(new_content) > 2000:
            raise ValueError("Memory content must contain 1 to 2000 characters.")
        if new_category not in MEMORY_CATEGORIES:
            raise ValueError(f"Unsupported memory category '{new_category}'.")
        new_tags = current["tags"] if tags is None else list(
            dict.fromkeys(tag.strip() for tag in tags if tag.strip())
        )[:10]
        if any(len(tag) > 50 for tag in new_tags):
            raise ValueError("Memory tags must not exceed 50 characters.")
        new_source = current["source"] if source is None else source.strip()
        if len(new_source) > 500:
            raise ValueError("Memory source must not exceed 500 characters.")
        with self.database.connection() as connection:
            duplicate = connection.execute(
                """
                SELECT id FROM memories
                WHERE category = ? AND normalized_content = ? AND id != ?
                """,
                (new_category, _normalize_content(new_content), memory_id),
            ).fetchone()
            if duplicate:
                raise ValueError(
                    f"This update duplicates existing memory '{duplicate['id']}'."
                )
            connection.execute(
                """
                UPDATE memories SET category = ?, content = ?,
                    normalized_content = ?, updated_at = ?, tags_json = ?,
                    source = ?
                WHERE id = ?
                """,
                (
                    new_category,
                    new_content,
                    _normalize_content(new_content),
                    _utc_now(),
                    json.dumps(new_tags),
                    new_source,
                    memory_id,
                ),
            )
        updated = self.get_memory(memory_id)
        if updated is None:
            raise RuntimeError("Updated memory could not be retrieved.")
        return updated

    def delete_memory(self, memory_id: str) -> bool:
        with self.database.connection() as connection:
            cursor = connection.execute(
                "DELETE FROM memories WHERE id = ?", (memory_id,)
            )
            return cursor.rowcount > 0

    def search_memories(
        self, query: str, limit: int = 5
    ) -> list[dict[str, Any]]:
        if not 1 <= limit <= 10:
            raise ValueError("Memory search limit must be between 1 and 10.")
        terms = _search_terms(query)
        if not terms:
            return []
        with self.database.connection() as connection:
            if self.database.fts5_available:
                rows = connection.execute(
                    """
                    SELECT m.* FROM memory_fts f
                    JOIN memories m ON m.id = f.memory_id
                    WHERE memory_fts MATCH ?
                    ORDER BY bm25(memory_fts)
                    LIMIT ?
                    """,
                    (_fts_query(terms), limit),
                ).fetchall()
            else:
                conditions = " OR ".join(
                    "instr(lower(content), lower(?)) > 0" for _ in terms
                )
                rows = connection.execute(
                    f"SELECT * FROM memories WHERE {conditions} "
                    "ORDER BY updated_at DESC LIMIT ?",
                    (*terms, limit),
                ).fetchall()
        return [self._memory_dict(row) for row in rows]

    def search_conversations(
        self, query: str, limit: int = 5
    ) -> list[dict[str, Any]]:
        if not 1 <= limit <= 10:
            raise ValueError("Conversation search limit must be between 1 and 10.")
        terms = _search_terms(query)
        if not terms:
            return []
        with self.database.connection() as connection:
            if self.database.fts5_available:
                rows = connection.execute(
                    """
                    SELECT conversation_id, content, bm25(conversation_fts) AS rank
                    FROM conversation_fts
                    WHERE conversation_fts MATCH ?
                    ORDER BY rank
                    LIMIT ?
                    """,
                    (_fts_query(terms), limit * 3),
                ).fetchall()
            else:
                conditions = " OR ".join(
                    "instr(lower(m.content), lower(?)) > 0" for _ in terms
                )
                rows = connection.execute(
                    f"""
                    SELECT m.conversation_id, m.content, 0 AS rank
                    FROM messages m WHERE {conditions}
                    ORDER BY m.id DESC LIMIT ?
                    """,
                    (*terms, limit * 3),
                ).fetchall()

            unique_ids: list[str] = []
            snippets: dict[str, str] = {}
            for row in rows:
                conversation_id = row["conversation_id"]
                if conversation_id not in snippets:
                    unique_ids.append(conversation_id)
                    snippets[conversation_id] = row["content"][:400]
                if len(unique_ids) >= limit:
                    break
            if not unique_ids:
                return []
            placeholders = ",".join("?" for _ in unique_ids)
            conversations = connection.execute(
                f"""
                SELECT id, title, created_at, updated_at, archived_at
                FROM conversations WHERE id IN ({placeholders})
                """,
                unique_ids,
            ).fetchall()
        by_id = {row["id"]: dict(row) for row in conversations}
        return [
            {**by_id[conversation_id], "snippet": snippets[conversation_id]}
            for conversation_id in unique_ids
            if conversation_id in by_id
        ]
