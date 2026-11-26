import asyncio
import inspect
import json
import logging
import math
import time
from dataclasses import dataclass
from enum import Enum
from typing import Any, Awaitable, Callable

from pydantic import BaseModel, ValidationError

logger = logging.getLogger(__name__)
MAX_TOOL_TIMEOUT_SECONDS = 120.0
MAX_APPROVAL_WAIT_SECONDS = 120.0


class ToolRisk(str, Enum):
    READ_ONLY = "read_only"
    LOW_IMPACT = "low_impact"
    MODERATE = "moderate"
    HIGH = "high"


class ApprovalPolicy(str, Enum):
    NEVER = "never"
    ALWAYS = "always"


class ToolStatus(str, Enum):
    SUCCEEDED = "succeeded"
    DENIED = "denied"
    VALIDATION_FAILURE = "validation_failure"
    TIMEOUT = "timeout"
    EXECUTION_FAILURE = "execution_failure"


@dataclass(frozen=True)
class ApprovalRequest:
    tool_name: str
    risk: ToolRisk
    arguments_json: str


@dataclass(frozen=True)
class ToolExecution:
    name: str
    status: ToolStatus
    content: str
    duration_ms: float
    operation_may_still_be_running: bool = False

    @property
    def succeeded(self) -> bool:
        return self.status is ToolStatus.SUCCEEDED


@dataclass(frozen=True)
class ToolDefinition:
    name: str
    description: str
    arguments_model: type[BaseModel]
    handler: Callable[[BaseModel], Any]
    risk: ToolRisk
    approval_policy: ApprovalPolicy
    timeout_seconds: float = 10.0

    def __post_init__(self) -> None:
        if not isinstance(self.risk, ToolRisk):
            raise ValueError("Every tool must declare a valid risk classification.")
        if not isinstance(self.approval_policy, ApprovalPolicy):
            raise ValueError("Every tool must declare a valid approval policy.")
        if (
            not math.isfinite(self.timeout_seconds)
            or not 0 < self.timeout_seconds <= MAX_TOOL_TIMEOUT_SECONDS
        ):
            raise ValueError(
                "Tool timeout must be greater than zero and at most "
                f"{MAX_TOOL_TIMEOUT_SECONDS:g} seconds."
            )
        if (
            self.risk is ToolRisk.HIGH
            and self.approval_policy is not ApprovalPolicy.ALWAYS
        ):
            raise ValueError("High-risk tools must always require approval.")


ApprovalCallback = Callable[
    [ApprovalRequest], bool | Awaitable[bool | None] | None
]


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, ToolDefinition] = {}
        self._background_tasks: set[asyncio.Task[Any]] = set()

    def register(self, definition: ToolDefinition) -> None:
        if definition.name in self._tools:
            raise ValueError(f"Tool '{definition.name}' is already registered.")
        self._tools[definition.name] = definition

    def _retain_background_task(
        self, task: asyncio.Task[Any], name: str, operation: str
    ) -> None:
        self._background_tasks.add(task)

        def finish(completed: asyncio.Task[Any]) -> None:
            self._background_tasks.discard(completed)
            try:
                completed.result()
            except asyncio.CancelledError:
                logger.info("Timed-out %s task was cancelled: %s", operation, name)
            except Exception as exc:
                logger.error(
                    "Timed-out %s task later failed for %s (%s)",
                    operation,
                    name,
                    type(exc).__name__,
                )
            else:
                logger.info(
                    "Timed-out %s task later completed: %s", operation, name
                )

        task.add_done_callback(finish)

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

    @staticmethod
    def _execution(
        name: str,
        status: ToolStatus,
        duration_ms: float,
        *,
        result: Any = None,
        error: Any = None,
        operation_may_still_be_running: bool = False,
    ) -> ToolExecution:
        payload: dict[str, Any] = {
            "tool": name,
            "status": status.value,
            "duration_ms": round(duration_ms, 2),
        }
        if status is ToolStatus.SUCCEEDED:
            payload["result"] = result
        if error is not None:
            payload["error"] = error
        if operation_may_still_be_running:
            payload["operation_may_still_be_running"] = True
        return ToolExecution(
            name=name,
            status=status,
            content=json.dumps(payload, ensure_ascii=True, default=str),
            duration_ms=duration_ms,
            operation_may_still_be_running=operation_may_still_be_running,
        )

    async def execute(
        self,
        name: str,
        arguments: dict[str, Any],
        confirm: ApprovalCallback | None = None,
    ) -> ToolExecution:
        started = time.monotonic()
        tool = self._tools.get(name)
        if tool is None:
            return self._execution(
                name,
                ToolStatus.VALIDATION_FAILURE,
                (time.monotonic() - started) * 1000,
                error=f"Unknown tool '{name}'.",
            )

        try:
            parsed_arguments = tool.arguments_model.model_validate(arguments)
        except ValidationError as exc:
            return self._execution(
                name,
                ToolStatus.VALIDATION_FAILURE,
                (time.monotonic() - started) * 1000,
                error={
                    "message": "Invalid tool arguments.",
                    "details": exc.errors(include_context=False),
                },
            )

        validated = parsed_arguments.model_dump(mode="json")
        arguments_json = json.dumps(
            validated, ensure_ascii=True, sort_keys=True, separators=(",", ":")
        )
        if tool.approval_policy is ApprovalPolicy.ALWAYS:
            if confirm is None:
                return self._execution(
                    name,
                    ToolStatus.DENIED,
                    (time.monotonic() - started) * 1000,
                    error="No approval decision was provided; tool was not executed.",
                )
            request = ApprovalRequest(
                tool_name=tool.name,
                risk=tool.risk,
                arguments_json=arguments_json,
            )
            try:
                approval_result = confirm(request)
                if inspect.isawaitable(approval_result):
                    async def resolve_approval() -> Any:
                        return await approval_result

                    approval_task = asyncio.create_task(resolve_approval())
                    completed, _ = await asyncio.wait(
                        {approval_task},
                        timeout=MAX_APPROVAL_WAIT_SECONDS,
                    )
                    if not completed:
                        self._retain_background_task(
                            approval_task, name, "approval"
                        )
                        return self._execution(
                            name,
                            ToolStatus.DENIED,
                            (time.monotonic() - started) * 1000,
                            error=(
                                "Approval decision timed out; "
                                "tool was not executed."
                            ),
                        )
                    if approval_task.cancelled():
                        return self._execution(
                            name,
                            ToolStatus.DENIED,
                            (time.monotonic() - started) * 1000,
                            error=(
                                "Approval decision was cancelled; "
                                "tool was not executed."
                            ),
                        )
                    approved = approval_task.result()
                else:
                    approved = approval_result
            except Exception as exc:
                logger.error(
                    "Tool approval callback failed for %s (%s)",
                    name,
                    type(exc).__name__,
                )
                return self._execution(
                    name,
                    ToolStatus.EXECUTION_FAILURE,
                    (time.monotonic() - started) * 1000,
                    error="Approval could not be obtained; tool was not executed.",
                )
            if approved is not True:
                logger.info("Tool execution denied: %s", name)
                return self._execution(
                    name,
                    ToolStatus.DENIED,
                    (time.monotonic() - started) * 1000,
                    error="User denied this action.",
                )

        async def invoke_handler() -> Any:
            if inspect.iscoroutinefunction(tool.handler):
                result = await tool.handler(parsed_arguments)
            else:
                result = await asyncio.to_thread(
                    tool.handler, parsed_arguments
                )
            if inspect.isawaitable(result):
                return await result
            return result

        handler_task = asyncio.create_task(invoke_handler())
        try:
            completed, _ = await asyncio.wait(
                {handler_task},
                timeout=tool.timeout_seconds,
            )
        except asyncio.CancelledError:
            self._retain_background_task(handler_task, name, "execution")
            raise
        if not completed:
            self._retain_background_task(handler_task, name, "execution")
            logger.warning(
                "Tool execution timed out; operation may still be running: %s",
                name,
            )
            return self._execution(
                name,
                ToolStatus.TIMEOUT,
                (time.monotonic() - started) * 1000,
                error=f"Tool exceeded its {tool.timeout_seconds:g}s time limit.",
                operation_may_still_be_running=True,
            )
        try:
            result = handler_task.result()
        except asyncio.CancelledError:
            return self._execution(
                name,
                ToolStatus.EXECUTION_FAILURE,
                (time.monotonic() - started) * 1000,
                error="Tool handler was cancelled.",
                operation_may_still_be_running=True,
            )
        except Exception as exc:
            logger.error(
                "Tool execution failed for %s (%s)",
                name,
                type(exc).__name__,
            )
            return self._execution(
                name,
                ToolStatus.EXECUTION_FAILURE,
                (time.monotonic() - started) * 1000,
                error=f"Tool '{name}' failed: {exc}",
            )

        logger.info("Tool executed: %s", name)
        return self._execution(
            name,
            ToolStatus.SUCCEEDED,
            (time.monotonic() - started) * 1000,
            result=result,
        )
