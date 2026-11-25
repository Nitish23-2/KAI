import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator
from uuid import uuid4


class Database:
    def __init__(self, path: Path) -> None:
        self.path = path
        if str(path) != ":memory:":
            path.parent.mkdir(parents=True, exist_ok=True)
        self.fts5_available = False
        self.initialize()

    @contextmanager
    def connection(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path, timeout=5.0)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    @staticmethod
    def _columns(
        connection: sqlite3.Connection, table: str
    ) -> set[str]:
        return {
            row["name"]
            for row in connection.execute(f"PRAGMA table_info({table})")
        }

    def initialize(self) -> None:
        with self.connection() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS conversations (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL DEFAULT '',
                    archived_at TEXT
                );

                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    conversation_id TEXT NOT NULL
                        REFERENCES conversations(id) ON DELETE CASCADE,
                    role TEXT NOT NULL
                        CHECK (role IN ('user', 'assistant', 'tool')),
                    content TEXT NOT NULL,
                    tool_calls_json TEXT,
                    tool_name TEXT,
                    tool_call_id TEXT,
                    memory_ids_json TEXT,
                    created_at TEXT NOT NULL DEFAULT ''
                );

                CREATE INDEX IF NOT EXISTS idx_messages_conversation
                    ON messages(conversation_id, id);
                """
            )

            conversation_columns = self._columns(connection, "conversations")
            if "title" not in conversation_columns:
                connection.execute(
                    "ALTER TABLE conversations ADD COLUMN title TEXT NOT NULL DEFAULT ''"
                )
            if "updated_at" not in conversation_columns:
                connection.execute(
                    "ALTER TABLE conversations ADD COLUMN updated_at TEXT NOT NULL DEFAULT ''"
                )
            if "archived_at" not in conversation_columns:
                connection.execute(
                    "ALTER TABLE conversations ADD COLUMN archived_at TEXT"
                )
            connection.execute(
                """
                UPDATE conversations SET updated_at = created_at
                WHERE updated_at = ''
                """
            )

            message_columns = self._columns(connection, "messages")
            if "created_at" not in message_columns:
                connection.execute(
                    "ALTER TABLE messages ADD COLUMN created_at TEXT NOT NULL DEFAULT ''"
                )
            if "tool_call_id" not in message_columns:
                connection.execute(
                    "ALTER TABLE messages ADD COLUMN tool_call_id TEXT"
                )
            if "memory_ids_json" not in message_columns:
                connection.execute(
                    "ALTER TABLE messages ADD COLUMN memory_ids_json TEXT"
                )
            connection.execute(
                """
                UPDATE messages
                SET created_at = COALESCE(
                    (SELECT created_at FROM conversations
                     WHERE conversations.id = messages.conversation_id),
                    ''
                )
                WHERE created_at = ''
                """
            )

            memory_columns = self._columns(connection, "memories")
            legacy_memory_table = bool(memory_columns) and (
                "category" not in memory_columns
                or "normalized_content" not in memory_columns
            )
            if legacy_memory_table:
                connection.execute(
                    "ALTER TABLE memories RENAME TO memories_legacy"
                )

            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS memories (
                    id TEXT PRIMARY KEY,
                    category TEXT NOT NULL CHECK (
                        category IN (
                            'user_preference', 'personal_profile',
                            'education_work', 'project', 'workflow',
                            'explicit_fact'
                        )
                    ),
                    content TEXT NOT NULL,
                    normalized_content TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    tags_json TEXT NOT NULL DEFAULT '[]',
                    source TEXT NOT NULL DEFAULT ''
                );

                CREATE UNIQUE INDEX IF NOT EXISTS idx_memories_category_content
                    ON memories(category, normalized_content);

                CREATE INDEX IF NOT EXISTS idx_conversations_updated
                    ON conversations(updated_at DESC);
                """
            )

            if legacy_memory_table:
                legacy_rows = connection.execute(
                    "SELECT content, created_at FROM memories_legacy"
                ).fetchall()
                for row in legacy_rows:
                    content = row["content"].strip()
                    if not content:
                        continue
                    normalized = " ".join(content.casefold().split())
                    connection.execute(
                        """
                        INSERT OR IGNORE INTO memories
                            (id, category, content, normalized_content,
                             created_at, updated_at, tags_json, source)
                        VALUES (
                            ?, 'explicit_fact', ?, ?, ?, ?, '[]',
                            'Migrated from KAI v0.1'
                        )
                        """,
                        (
                            str(uuid4()),
                            content,
                            normalized,
                            row["created_at"],
                            row["created_at"],
                        ),
                    )
                connection.execute("DROP TABLE memories_legacy")

            try:
                connection.executescript(
                    """
                    CREATE VIRTUAL TABLE IF NOT EXISTS memory_fts USING fts5(
                        memory_id UNINDEXED, content, tags, category UNINDEXED,
                        tokenize='unicode61'
                    );
                    CREATE VIRTUAL TABLE IF NOT EXISTS conversation_fts USING fts5(
                        conversation_id UNINDEXED, content,
                        tokenize='unicode61'
                    );

                    CREATE TRIGGER IF NOT EXISTS memories_fts_insert
                    AFTER INSERT ON memories BEGIN
                        INSERT INTO memory_fts
                            (memory_id, content, tags, category)
                        VALUES (
                            new.id, new.content, new.tags_json, new.category
                        );
                    END;

                    CREATE TRIGGER IF NOT EXISTS memories_fts_delete
                    AFTER DELETE ON memories BEGIN
                        DELETE FROM memory_fts WHERE memory_id = old.id;
                    END;

                    CREATE TRIGGER IF NOT EXISTS memories_fts_update
                    AFTER UPDATE ON memories BEGIN
                        DELETE FROM memory_fts WHERE memory_id = old.id;
                        INSERT INTO memory_fts
                            (memory_id, content, tags, category)
                        VALUES (
                            new.id, new.content, new.tags_json, new.category
                        );
                    END;

                    CREATE TRIGGER IF NOT EXISTS messages_fts_insert
                    AFTER INSERT ON messages BEGIN
                        INSERT INTO conversation_fts
                            (rowid, conversation_id, content)
                        VALUES (new.id, new.conversation_id, new.content);
                    END;

                    INSERT INTO memory_fts
                        (memory_id, content, tags, category)
                    SELECT m.id, m.content, m.tags_json, m.category
                    FROM memories AS m
                    WHERE NOT EXISTS (
                        SELECT 1 FROM memory_fts f WHERE f.memory_id = m.id
                    );

                    INSERT INTO conversation_fts
                        (rowid, conversation_id, content)
                    SELECT m.id, m.conversation_id, m.content
                    FROM messages AS m
                    WHERE NOT EXISTS (
                        SELECT 1 FROM conversation_fts f WHERE f.rowid = m.id
                    );
                    """
                )
                self.fts5_available = True
            except sqlite3.OperationalError as exc:
                if "fts5" not in str(exc).casefold():
                    raise
                self.fts5_available = False
