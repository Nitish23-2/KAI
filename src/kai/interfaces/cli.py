import asyncio
import logging
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

    database = Database(settings.database_path)
    repository = Repository(database)
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

    engine = AssistantEngine(
        client, registry, repository, settings.max_tool_rounds
    )
    conversation_id = repository.create_conversation()
    print(
        f"KAI is ready (model: {settings.model}). Type /help for commands."
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
        if command in {"/exit", "/quit"}:
            print("KAI: Goodbye.")
            return 0
        if command == "/help":
            print("Commands: /help, /reset, /exit, /quit")
            continue
        if command == "/reset":
            conversation_id = repository.create_conversation()
            print("KAI: Started a new conversation. Earlier history is retained.")
            continue
        try:
            response = await engine.respond(
                conversation_id, user_text, _confirm_action
            )
            print(f"\nKAI: {response}")
        except (OllamaError, ValueError) as exc:
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
