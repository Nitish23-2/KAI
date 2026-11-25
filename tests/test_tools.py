import json

from kai.tools.builtin import register_builtin_tools
from kai.tools.registry import ToolDefinition, ToolRegistry
from pydantic import BaseModel


def _deny_confirmation(_: str, __: dict) -> bool:
    return False


def test_invalid_arguments_are_rejected(repository) -> None:
    registry = ToolRegistry()
    register_builtin_tools(registry, repository)

    result = registry.execute(
        "open_website", {"url": "file:///C:/Windows/win.ini"}, _deny_confirmation
    )

    assert not result.succeeded
    assert "Invalid tool arguments" in result.content


def test_confirmation_prevents_memory_write(repository) -> None:
    registry = ToolRegistry()
    register_builtin_tools(registry, repository)

    result = registry.execute(
        "save_memory", {"content": "should not persist"}, _deny_confirmation
    )

    assert not result.succeeded
    assert repository.search_memories("should not persist") == []


def test_memory_tools_create_update_and_delete_with_confirmation(
    repository,
) -> None:
    registry = ToolRegistry()
    register_builtin_tools(registry, repository)
    approvals = []

    def approve(name, arguments):
        approvals.append((name, arguments))
        return True

    created = registry.execute(
        "save_memory",
        {
            "content": "Prefers concise emails",
            "category": "user_preference",
            "tags": ["email"],
        },
        approve,
    )
    memory = json.loads(created.content)
    memory_id = memory["id"]
    updated = registry.execute(
        "update_memory",
        {"memory_id": memory_id, "content": "Prefers concise work emails"},
        approve,
    )
    assert json.loads(updated.content)["content"] == (
        "Prefers concise work emails"
    )
    deleted = registry.execute(
        "delete_memory", {"memory_id": memory_id}, approve
    )

    assert json.loads(deleted.content)["deleted"] is True
    assert [name for name, _ in approvals] == [
        "save_memory", "update_memory", "delete_memory"
    ]
    assert repository.get_memory(memory_id) is None


def test_invalid_memory_is_reported_as_json(repository) -> None:
    registry = ToolRegistry()
    register_builtin_tools(registry, repository)

    result = registry.execute(
        "save_memory", {"content": "   "}, _deny_confirmation
    )

    assert not result.succeeded
    assert json.loads(result.content)["error"] == "Invalid tool arguments."


def test_memory_write_database_failure_is_reported(repository, monkeypatch) -> None:
    def fail_connection():
        raise RuntimeError("database is locked")

    monkeypatch.setattr(repository.database, "connection", fail_connection)
    registry = ToolRegistry()
    register_builtin_tools(registry, repository)

    result = registry.execute(
        "save_memory",
        {"content": "A test preference", "category": "user_preference"},
        lambda *_: True,
    )

    assert not result.succeeded
    assert "database is locked" in result.content


def test_invalid_memory_category_does_not_save(repository) -> None:
    registry = ToolRegistry()
    register_builtin_tools(registry, repository)

    result = registry.execute(
        "save_memory",
        {"content": "A test preference", "category": "medical_record"},
        lambda *_: True,
    )

    assert not result.succeeded
    assert repository.list_memories() == []


def test_website_is_opened_only_after_approval(
    repository, monkeypatch
) -> None:
    opened_urls = []
    monkeypatch.setattr(
        "kai.tools.builtin.webbrowser.open",
        lambda url, new: opened_urls.append((url, new)) or True,
    )
    registry = ToolRegistry()

    register_builtin_tools(registry, repository)
    result = registry.execute(
        "open_website",
        {"url": "https://example.com"},
        lambda *_: True,
    )

    assert result.succeeded
    assert opened_urls == [("https://example.com/", 2)]


def test_unregistered_tool_is_rejected() -> None:
    result = ToolRegistry().execute(
        "run_shell", {"command": "whoami"}, _deny_confirmation
    )

    assert not result.succeeded
    assert "Unknown tool" in result.content


def test_duplicate_registration_is_rejected() -> None:
    class EmptyArguments(BaseModel):
        pass

    registry = ToolRegistry()
    definition = ToolDefinition(
        name="sample",
        description="A test tool.",
        arguments_model=EmptyArguments,
        handler=lambda _: {"ok": True},
    )
    registry.register(definition)

    try:
        registry.register(definition)
    except ValueError as exc:
        assert "already registered" in str(exc)
    else:
        raise AssertionError("Duplicate tool registration should fail.")
