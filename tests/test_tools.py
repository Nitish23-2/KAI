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


def test_invalid_memory_is_reported_as_json(repository) -> None:
    registry = ToolRegistry()
    register_builtin_tools(registry, repository)

    result = registry.execute(
        "save_memory", {"content": "   "}, _deny_confirmation
    )

    assert not result.succeeded
    assert json.loads(result.content)["error"] == "Invalid tool arguments."


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
