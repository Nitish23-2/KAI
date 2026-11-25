import asyncio
import logging
import sqlite3
from typing import Any

from kai.ai.engine import AssistantEngine
from kai.ai.ollama import OllamaClient, OllamaError
from kai.config import Settings
from kai.logging_config import configure_logging
from kai.storage.database import Database
from kai.storage.repository import Repository
from kai.tools.builtin import register_builtin_tools
from kai.tools.registry import ToolRegistry

logger = logging.getLogger(__name__)


def _confirm_action(tool_name: str, arguments: dict[str, Any]) -> bool:
    print(f"\nKAI requests permission to run '{tool_name}': {arguments}")
    try:
        answer = input("Allow this action? [y/N]: ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        print()
        return False
    return answer in {"y", "yes"}


async def _run() -> int:
    try:
        settings = Settings.from_env()
    except ValueError as exc:
        print(f"Configuration error: {exc}")
        return 2

    try:
        database = Database(settings.database_path)
        repository = Repository(database)
    except (sqlite3.Error, OSError) as exc:
        logger.exception("Could not initialize local database")
        print(f"Cannot initialize KAI database: {exc}")
        return 1
    registry = ToolRegistry()
    register_builtin_tools(registry, repository)
    client = OllamaClient(
        settings.ollama_url,
        settings.model,
        settings.request_timeout_seconds,
        settings.context_size,
    )
    try:
        await client.ensure_model_available()
    except OllamaError as exc:
        print(f"Cannot start KAI: {exc}")
        return 1

    try:
        conversation_id = repository.create_conversation()
    except sqlite3.Error as exc:
        logger.exception("Could not create conversation")
        print(f"Cannot create a conversation: {exc}")
        return 1

    engine = AssistantEngine(
        client, registry, repository, settings.max_tool_rounds
    )
    print(
        f"KAI is ready (model: {settings.model}). "
        "Type /help for commands."
    )
    while True:
        try:
            user_text = input("\nYou: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nKAI: Goodbye.")
            return 0
        if not user_text:
            continue
        command = user_text.lower()
        command_name, _, command_argument = user_text.partition(" ")
        command_argument = command_argument.strip()
        if command in {"/exit", "/quit"}:
            print("KAI: Goodbye.")
            return 0
        if command == "/help":
            print(
                "Commands: /help, /reset, /conversations [all], "
                "/resume <id>, /title <title>, /archive [id], /exit, /quit"
            )
            continue
        if command == "/reset":
            conversation_id = repository.create_conversation()
            print("KAI: Started a new conversation. Earlier history is retained.")
            continue
        if command_name.lower() == "/conversations":
            conversations = repository.list_conversations(
                limit=20,
                include_archived=command_argument.lower() == "all",
            )
            if not conversations:
                print("KAI: No saved conversations found.")
                continue
            for item in conversations:
                title = item["title"] or "Untitled conversation"
                archived = " [archived]" if item["archived_at"] else ""
                print(
                    f"{item['id']} | {title} | "
                    f"{item['updated_at']} | {item['message_count']} messages"
                    f"{archived}"
                )
            continue
        if command_name.lower() == "/resume":
            if not command_argument:
                print("Usage: /resume <conversation-id>")
                continue
            conversation = repository.get_conversation(command_argument)
            if conversation is None:
                print("KAI: That conversation was not found.")
            elif conversation["archived_at"]:
                print(
                    "KAI: That conversation is archived; "
                    "unarchive is not available."
                )
            else:
                conversation_id = command_argument
                title = conversation["title"] or "Untitled conversation"
                print(f"KAI: Resumed '{title}'.")
            continue
        if command_name.lower() == "/title":
            if not command_argument:
                print("Usage: /title <new title>")
                continue
            try:
                repository.set_conversation_title(
                    conversation_id, command_argument
                )
                print("KAI: Conversation title updated.")
            except (KeyError, ValueError) as exc:
                print(f"KAI: Could not update title: {exc}")
            continue
        if command_name.lower() == "/archive":
            target_id = command_argument or conversation_id
            try:
                repository.archive_conversation(target_id)
                print("KAI: Conversation archived.")
                if target_id == conversation_id:
                    conversation_id = repository.create_conversation()
                    print("KAI: Started a new conversation.")
            except KeyError as exc:
                print(f"KAI: Could not archive conversation: {exc}")
            continue
        try:
            response = await engine.respond(
                conversation_id, user_text, _confirm_action
            )
            print(f"\nKAI: {response}")
        except (OllamaError, ValueError, KeyError, sqlite3.Error) as exc:
            logger.error("Request failed: %s", exc)
            print(f"\nKAI could not complete that request: {exc}")


def main() -> None:
    configure_logging()
    try:
        exit_code = asyncio.run(_run())
    except KeyboardInterrupt:
        print("\nKAI: Goodbye.")
        exit_code = 0
    raise SystemExit(exit_code)
