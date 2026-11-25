import json
import logging
from dataclasses import dataclass
from typing import Any, Callable

from pydantic import BaseModel, ValidationError

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ToolExecution:
    name: str
    content: str
    succeeded: bool


@dataclass(frozen=True)
class ToolDefinition:
    name: str
    description: str
    arguments_model: type[BaseModel]
    handler: Callable[[BaseModel], Any]
    requires_confirmation: bool = False


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, ToolDefinition] = {}

    def register(self, definition: ToolDefinition) -> None:
        if definition.name in self._tools:
            raise ValueError(f"Tool '{definition.name}' is already registered.")
        self._tools[definition.name] = definition

    def schemas(self, names: set[str] | None = None) -> list[dict[str, Any]]:
        return [
            {
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.arguments_model.model_json_schema(),
                },
            }
            for tool in self._tools.values()
            if names is None or tool.name in names
        ]

    def execute(
        self,
        name: str,
        arguments: dict[str, Any],
        confirm: Callable[[str, dict[str, Any]], bool],
    ) -> ToolExecution:
        tool = self._tools.get(name)
        if tool is None:
            return ToolExecution(
                name=name,
                content=json.dumps({"error": f"Unknown tool '{name}'."}),
                succeeded=False,
            )
        try:
            parsed_arguments = tool.arguments_model.model_validate(arguments)
        except ValidationError as exc:
            return ToolExecution(
                name=name,
                content=json.dumps(
                    {
                        "error": "Invalid tool arguments.",
                        "details": exc.errors(include_context=False),
                    }
                ),
                succeeded=False,
            )

        validated = parsed_arguments.model_dump(mode="json")
        if tool.requires_confirmation and not confirm(name, validated):
            logger.info("Tool execution declined: %s", name)
            return ToolExecution(
                name=name,
                content=json.dumps({"error": "User declined this action."}),
                succeeded=False,
            )
        try:
            result = tool.handler(parsed_arguments)
        except Exception as exc:
            logger.exception("Tool execution failed: %s", name)
            return ToolExecution(
                name=name,
                content=json.dumps(
                    {"error": f"Tool '{name}' failed: {exc}"}
                ),
                succeeded=False,
            )

        logger.info("Tool executed: %s", name)
        return ToolExecution(
            name=name,
            content=json.dumps(result, ensure_ascii=True, default=str),
            succeeded=True,
        )
