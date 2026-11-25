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

    assert repository.get_messages(conversation_id) == [
        {"role": "assistant", "content": "", "tool_calls": tool_calls}
    ]
