from datetime import datetime
from typing import Any
from urllib.parse import urlsplit
import webbrowser

from pydantic import AnyHttpUrl, BaseModel, ConfigDict, Field, field_validator

from kai.storage.repository import Repository
from kai.tools.registry import ToolDefinition, ToolRegistry


class StrictArguments(BaseModel):
    model_config = ConfigDict(extra="forbid")


class NoArguments(StrictArguments):
    pass


class OpenWebsiteArguments(StrictArguments):
    url: AnyHttpUrl


class SaveMemoryArguments(StrictArguments):
    content: str = Field(min_length=1, max_length=2000)

    @field_validator("content")
    @classmethod
    def content_must_not_be_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Memory content cannot be blank.")
        return value


class SearchMemoriesArguments(StrictArguments):
    query: str = Field(min_length=1, max_length=200)
    limit: int = Field(default=5, ge=1, le=10)

    @field_validator("query")
    @classmethod
    def query_must_not_be_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Memory search query cannot be blank.")
        return value


def register_builtin_tools(
    registry: ToolRegistry, repository: Repository
) -> None:
    def current_datetime(_: BaseModel) -> dict[str, str]:
        now = datetime.now().astimezone()
        return {"local_datetime": now.isoformat(), "timezone": str(now.tzinfo)}

    def open_website(arguments: BaseModel) -> dict[str, Any]:
        url = str(arguments.url)
        if urlsplit(url).scheme not in {"http", "https"}:
            raise ValueError("Only HTTP and HTTPS websites can be opened.")
        if not webbrowser.open(url, new=2):
            raise RuntimeError("The system browser did not accept the URL.")
        return {"opened": True, "url": url}

    def save_memory(arguments: BaseModel) -> dict[str, Any]:
        memory = arguments
        assert isinstance(memory, SaveMemoryArguments)
        memory_id = repository.save_memory(memory.content)
        return {"saved": True, "memory_id": memory_id}

    def search_memories(arguments: BaseModel) -> list[dict[str, Any]]:
        search = arguments
        assert isinstance(search, SearchMemoriesArguments)
        return repository.search_memories(search.query, search.limit)

    registry.register(
        ToolDefinition(
            name="get_current_datetime",
            description="Get the current local date, time, and timezone.",
            arguments_model=NoArguments,
            handler=current_datetime,
        )
    )
    registry.register(
        ToolDefinition(
            name="open_website",
            description=(
                "Open a user-requested HTTP or HTTPS website in the system "
                "browser. Ask for the exact URL; the user must approve."
            ),
            arguments_model=OpenWebsiteArguments,
            handler=open_website,
            requires_confirmation=True,
        )
    )
    registry.register(
        ToolDefinition(
            name="save_memory",
            description=(
                "Save a user-approved fact or preference to persistent memory. "
                "Use only when the user explicitly asks KAI to remember it."
            ),
            arguments_model=SaveMemoryArguments,
            handler=save_memory,
            requires_confirmation=True,
        )
    )
    registry.register(
        ToolDefinition(
            name="search_memories",
            description="Search saved memories for text matching a query.",
            arguments_model=SearchMemoriesArguments,
            handler=search_memories,
        )
    )
