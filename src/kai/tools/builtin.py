from datetime import datetime
from typing import Any, Literal
from urllib.parse import urlsplit
import webbrowser

from pydantic import AnyHttpUrl, BaseModel, ConfigDict, Field, field_validator

from kai.storage.repository import Repository
from kai.tools.registry import ToolDefinition, ToolRegistry

MemoryCategory = Literal[
    "user_preference",
    "personal_profile",
    "education_work",
    "project",
    "workflow",
    "explicit_fact",
]


class StrictArguments(BaseModel):
    model_config = ConfigDict(extra="forbid")


class NoArguments(StrictArguments):
    pass


class OpenWebsiteArguments(StrictArguments):
    url: AnyHttpUrl


class SaveMemoryArguments(StrictArguments):
    content: str = Field(
        min_length=1,
        max_length=2000,
        description=(
            "A complete, self-contained fact, e.g. 'User prefers concise "
            "emails'; preserve the user's meaning."
        ),
    )
    category: MemoryCategory = Field(
        default="explicit_fact",
        description="Use user_preference for the user's stated preferences.",
    )
    tags: list[str] = Field(default_factory=list, max_length=10)
    source: str = Field(
        default="User explicitly requested this memory.", max_length=500
    )

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


class ListMemoriesArguments(StrictArguments):
    limit: int = Field(default=30, ge=1, le=100)


class MemoryIdArguments(StrictArguments):
    memory_id: str = Field(min_length=1, max_length=64)


class UpdateMemoryArguments(MemoryIdArguments):
    content: str | None = Field(default=None, min_length=1, max_length=2000)
    category: MemoryCategory | None = None
    tags: list[str] | None = Field(default=None, max_length=10)
    source: str | None = Field(default=None, max_length=500)


class ListConversationsArguments(StrictArguments):
    limit: int = Field(default=10, ge=1, le=20)
    include_archived: bool = False


class SearchConversationsArguments(StrictArguments):
    query: str = Field(min_length=1, max_length=200)
    limit: int = Field(default=5, ge=1, le=10)

    @field_validator("query")
    @classmethod
    def query_must_not_be_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Conversation search query cannot be blank.")
        return value


class GetConversationArguments(StrictArguments):
    conversation_id: str = Field(min_length=1, max_length=64)
    message_limit: int = Field(default=20, ge=1, le=40)


def register_builtin_tools(
    registry: ToolRegistry, repository: Repository
) -> None:
    def current_datetime(_: BaseModel) -> dict[str, str]:
        now = datetime.now().astimezone()
        return {"local_datetime": now.isoformat(), "timezone": str(now.tzinfo)}

    def open_website(arguments: BaseModel) -> dict[str, Any]:
        website = arguments
        assert isinstance(website, OpenWebsiteArguments)
        url = str(website.url)
        if urlsplit(url).scheme not in {"http", "https"}:
            raise ValueError("Only HTTP and HTTPS websites can be opened.")
        if not webbrowser.open(url, new=2):
            raise RuntimeError("The system browser did not accept the URL.")
        return {"opened": True, "url": url}

    def save_memory(arguments: BaseModel) -> dict[str, Any]:
        memory = arguments
        assert isinstance(memory, SaveMemoryArguments)
        return repository.create_memory(
            memory.content,
            memory.category,
            memory.tags,
            memory.source,
        )

    def search_memories(arguments: BaseModel) -> list[dict[str, Any]]:
        search = arguments
        assert isinstance(search, SearchMemoriesArguments)
        return repository.search_memories(search.query, search.limit)

    def list_memories(arguments: BaseModel) -> list[dict[str, Any]]:
        listing = arguments
        assert isinstance(listing, ListMemoriesArguments)
        return repository.list_memories(listing.limit)

    def update_memory(arguments: BaseModel) -> dict[str, Any]:
        update = arguments
        assert isinstance(update, UpdateMemoryArguments)
        return repository.update_memory(
            update.memory_id,
            update.content,
            update.category,
            update.tags,
            update.source,
        )

    def delete_memory(arguments: BaseModel) -> dict[str, Any]:
        deletion = arguments
        assert isinstance(deletion, MemoryIdArguments)
        return {
            "deleted": repository.delete_memory(deletion.memory_id),
            "memory_id": deletion.memory_id,
        }

    def list_conversations(arguments: BaseModel) -> list[dict[str, Any]]:
        listing = arguments
        assert isinstance(listing, ListConversationsArguments)
        return repository.list_conversations(
            listing.limit, listing.include_archived
        )

    def search_conversations(arguments: BaseModel) -> list[dict[str, Any]]:
        search = arguments
        assert isinstance(search, SearchConversationsArguments)
        return repository.search_conversations(search.query, search.limit)

    def get_conversation(arguments: BaseModel) -> dict[str, Any]:
        request = arguments
        assert isinstance(request, GetConversationArguments)
        conversation = repository.get_conversation(request.conversation_id)
        if conversation is None:
            return {"error": "Conversation not found."}
        messages = repository.get_messages(request.conversation_id)
        conversation["messages"] = [
            {
                key: value
                for key, value in message.items()
                if key != "created_at"
            }
            for message in messages[-request.message_limit :]
        ]
        return conversation

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
                "Save personal information only when the user explicitly "
                "asks KAI to remember it. Choose a category, useful tags, and "
                "a truthful brief source/reason. The user must approve."
            ),
            arguments_model=SaveMemoryArguments,
            handler=save_memory,
            requires_confirmation=True,
        )
    )
    registry.register(
        ToolDefinition(
            name="search_memories",
            description=(
                "Find saved memories relevant to a specific query. Use this "
                "for questions about remembered preferences or facts."
            ),
            arguments_model=SearchMemoriesArguments,
            handler=search_memories,
        )
    )
    registry.register(
        ToolDefinition(
            name="list_memories",
            description=(
                "List saved user memories with IDs and categories when the "
                "user asks what KAI remembers."
            ),
            arguments_model=ListMemoriesArguments,
            handler=list_memories,
        )
    )
    registry.register(
        ToolDefinition(
            name="update_memory",
            description=(
                "Correct or update a saved memory by its ID. Search memories "
                "first if its ID is not known. The user must approve changes."
            ),
            arguments_model=UpdateMemoryArguments,
            handler=update_memory,
            requires_confirmation=True,
        )
    )
    registry.register(
        ToolDefinition(
            name="delete_memory",
            description=(
                "Forget a saved memory by ID. Search memories first if the ID "
                "is not known. Confirm the exact deletion with the user."
            ),
            arguments_model=MemoryIdArguments,
            handler=delete_memory,
            requires_confirmation=True,
        )
    )
    registry.register(
        ToolDefinition(
            name="list_conversations",
            description=(
                "List recent saved conversations and their IDs when asked "
                "about previous sessions or to continue prior work."
            ),
            arguments_model=ListConversationsArguments,
            handler=list_conversations,
        )
    )
    registry.register(
        ToolDefinition(
            name="search_conversations",
            description=(
                "Search past conversation messages by topic when the user "
                "asks what was discussed or wants to continue earlier work."
            ),
            arguments_model=SearchConversationsArguments,
            handler=search_conversations,
        )
    )
    registry.register(
        ToolDefinition(
            name="get_conversation",
            description=(
                "Retrieve the title and recent messages for a saved "
                "conversation by ID, including its tool-call history."
            ),
            arguments_model=GetConversationArguments,
            handler=get_conversation,
        )
    )
