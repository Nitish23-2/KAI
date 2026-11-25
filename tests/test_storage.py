import sqlite3

from kai.storage.database import Database
from kai.storage.repository import Repository


def test_memory_persists_after_reopening_database(tmp_path) -> None:
    database_path = tmp_path / "kai.db"
    Repository(Database(database_path)).save_memory("Prefers concise summaries")

    restarted_repository = Repository(Database(database_path))

    results = restarted_repository.search_memories("concise")
    assert len(results) == 1
    assert results[0]["content"] == "Prefers concise summaries"


def test_conversation_messages_retain_tool_calls(repository) -> None:
    conversation_id = repository.create_conversation()
    tool_calls = [
        {"function": {"name": "get_current_datetime", "arguments": {}}}
    ]

    repository.add_message(
        conversation_id, "assistant", "", tool_calls=tool_calls
    )

    messages = repository.get_messages(conversation_id)
    assert messages[0]["role"] == "assistant"
    assert messages[0]["content"] == ""
    assert messages[0]["tool_calls"] == tool_calls
    assert messages[0]["created_at"]


def test_conversation_list_title_archive_and_resume(repository) -> None:
    conversation_id = repository.create_conversation()
    repository.add_message(conversation_id, "user", "Plan the KAI memory project")
    repository.add_message(conversation_id, "assistant", "Let's begin.")

    conversation = repository.get_conversation(conversation_id)
    assert conversation is not None
    assert conversation["title"] == "Plan the KAI memory project"
    assert conversation["updated_at"] >= conversation["created_at"]
    assert [item["id"] for item in repository.list_conversations()] == [
        conversation_id
    ]
    restarted_repository = Repository(Database(repository.database.path))
    assert [
        item["role"]
        for item in restarted_repository.get_messages(conversation_id)
    ] == ["user", "assistant"]

    repository.archive_conversation(conversation_id)

    assert repository.list_conversations() == []
    assert repository.list_conversations(include_archived=True)[0][
        "archived_at"
    ]


def test_tool_call_id_and_tool_history_are_preserved(repository) -> None:
    conversation_id = repository.create_conversation()
    calls = [
        {
            "id": "call-abc",
            "function": {"name": "search_memories", "arguments": {"query": "work"}},
        }
    ]
    repository.add_message(
        conversation_id, "assistant", "", tool_calls=calls
    )
    repository.add_message(
        conversation_id,
        "tool",
        '[{"content":"Works at KAI"}]',
        tool_name="search_memories",
        tool_call_id="call-abc",
    )

    messages = repository.get_messages(conversation_id)
    assert messages[0]["tool_calls"] == calls
    assert messages[1]["tool_call_id"] == "call-abc"
    assert messages[1]["name"] == "search_memories"


def test_memory_crud_category_tags_provenance_and_duplicate_detection(
    repository,
) -> None:
    created = repository.create_memory(
        "Prefers concise emails",
        category="user_preference",
        tags=["email", "style"],
        source="User explicitly asked to remember this.",
    )
    duplicate = repository.create_memory(
        "  PREFERS concise   emails ",
        category="user_preference",
    )

    assert duplicate["id"] == created["id"]
    assert duplicate["duplicate"] is True
    assert repository.get_memory(created["id"])["tags"] == ["email", "style"]
    updated = repository.update_memory(
        created["id"], content="Prefers concise professional emails"
    )
    assert updated["updated_at"] >= created["updated_at"]
    assert updated["source"] == "User explicitly asked to remember this."
    assert repository.search_memories("professional email")[0]["id"] == (
        created["id"]
    )
    assert repository.delete_memory(created["id"])
    assert repository.get_memory(created["id"]) is None
    with repository.database.connection() as connection:
        indexed_memory = connection.execute(
            "SELECT 1 FROM memory_fts WHERE memory_id = ?",
            (created["id"],),
        ).fetchone()
    assert indexed_memory is None
    assert repository.search_memories("professional email") == []


def test_memory_search_returns_relevant_results_only(repository) -> None:
    repository.create_memory(
        "Prefers concise emails", category="user_preference"
    )
    repository.create_memory(
        "Currently developing a personal assistant", category="project"
    )

    matches = repository.search_memories("email writing style")

    assert len(matches) == 1
    assert matches[0]["content"] == "Prefers concise emails"
    assert repository.search_memories("gardening") == []


def test_memory_search_fallback_without_fts5(repository) -> None:
    repository.create_memory(
        "Prefers concise emails", category="user_preference"
    )
    repository.database.fts5_available = False

    matches = repository.search_memories("concise email")

    assert len(matches) == 1
    assert matches[0]["content"] == "Prefers concise emails"


def test_memory_update_cannot_create_a_duplicate(repository) -> None:
    first = repository.create_memory(
        "Prefers concise emails", category="user_preference"
    )
    second = repository.create_memory(
        "Works as a software developer", category="education_work"
    )

    try:
        repository.update_memory(
            second["id"],
            content="Prefers concise emails",
            category="user_preference",
        )
    except ValueError as exc:
        assert "duplicates existing memory" in str(exc)
    else:
        raise AssertionError("An update must not duplicate another memory.")
    assert repository.get_memory(first["id"])["content"] == (
        "Prefers concise emails"
    )


def test_conversation_search_finds_previous_discussion(repository) -> None:
    conversation_id = repository.create_conversation("KAI memory roadmap")
    repository.add_message(
        conversation_id,
        "user",
        "We designed a SQLite FTS5 personal memory retrieval layer.",
    )

    results = repository.search_conversations("SQLite memory retrieval")

    assert results[0]["id"] == conversation_id
    assert "FTS5" in results[0]["snippet"]


def test_archived_conversation_keeps_searchable_tool_call_history(
    repository,
) -> None:
    conversation_id = repository.create_conversation("Previous project")
    call = {
        "id": "call-history",
        "function": {
            "name": "search_memories",
            "arguments": {"query": "migration"},
        },
    }
    repository.add_message(
        conversation_id, "assistant", "", tool_calls=[call]
    )
    repository.add_message(
        conversation_id,
        "tool",
        '{"result":"SQLite migration completed"}',
        tool_name="search_memories",
        tool_call_id="call-history",
    )

    repository.archive_conversation(conversation_id)

    assert repository.list_conversations() == []
    assert repository.list_conversations(include_archived=True)[0]["id"] == (
        conversation_id
    )
    historical = repository.search_conversations("SQLite migration")
    assert historical[0]["id"] == conversation_id
    messages = repository.get_messages(conversation_id)
    assert messages[0]["tool_calls"] == [call]
    assert messages[1]["tool_call_id"] == "call-history"
    assert messages[1]["name"] == "search_memories"


def test_phase_one_database_migrates_without_losing_records(tmp_path) -> None:
    database_path = tmp_path / "phase-one.db"
    with sqlite3.connect(database_path) as connection:
        connection.executescript(
            """
            CREATE TABLE conversations (
                id TEXT PRIMARY KEY, created_at TEXT NOT NULL
            );
            CREATE TABLE messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                conversation_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                tool_calls_json TEXT,
                tool_name TEXT
            );
            CREATE TABLE memories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                content TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            INSERT INTO conversations VALUES
                ('old-conversation', '2025-01-01T00:00:00+00:00');
            INSERT INTO messages
                (conversation_id, role, content, tool_calls_json, tool_name)
            VALUES
                ('old-conversation', 'user', 'Old conversation survives', NULL, NULL),
                (
                    'old-conversation', 'assistant', '',
                    '[{"function":{"name":"get_current_datetime","arguments":{}}}]',
                    NULL
                ),
                (
                    'old-conversation', 'tool',
                    '{"local_datetime":"2025-01-01T00:00:00+00:00"}',
                    NULL, 'get_current_datetime'
                );
            INSERT INTO memories (content, created_at) VALUES
                ('Existing v0.1 memory', '2025-01-01T00:00:00+00:00');
            """
        )

    database = Database(database_path)
    repository = Repository(database)

    migrated_messages = repository.get_messages("old-conversation")
    assert [message["role"] for message in migrated_messages] == [
        "user", "assistant", "tool"
    ]
    assert migrated_messages[0]["content"] == "Old conversation survives"
    assert migrated_messages[1]["tool_calls"][0]["function"]["name"] == (
        "get_current_datetime"
    )
    assert migrated_messages[2]["name"] == "get_current_datetime"
    migrated_memory = repository.search_memories("v0.1")
    assert migrated_memory[0]["content"] == "Existing v0.1 memory"
    assert migrated_memory[0]["source"] == "Migrated from KAI v0.1"
    assert len(migrated_memory[0]["id"]) == 36
    assert repository.get_conversation("old-conversation")["updated_at"] == (
        "2025-01-01T00:00:00+00:00"
    )
    migrated_memory_id = migrated_memory[0]["id"]

    Repository(Database(database_path))
    reopened = Repository(Database(database_path))
    assert reopened.get_memory(migrated_memory_id) is not None
    assert len(reopened.search_memories("v0.1")) == 1

def test_database_failure_is_not_silently_reported(repository, monkeypatch) -> None:
    def fail_connection():
        raise sqlite3.OperationalError("database is locked")

    monkeypatch.setattr(repository.database, "connection", fail_connection)

    try:
        repository.create_memory("A test fact")
    except sqlite3.OperationalError as exc:
        assert "locked" in str(exc)
    else:
        raise AssertionError("Database failure should be propagated.")
