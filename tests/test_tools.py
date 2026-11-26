import asyncio
import json
import threading

import pytest
from pydantic import BaseModel

import kai.tools.registry as registry_module
from kai.tools.builtin import register_builtin_tools
from kai.tools.registry import (
    ApprovalPolicy,
    ToolDefinition,
    ToolRegistry,
    ToolRisk,
    ToolStatus,
)


def _deny_confirmation(_) -> bool:
    return False


@pytest.mark.asyncio
async def test_invalid_arguments_are_rejected(repository) -> None:
    registry = ToolRegistry()
    register_builtin_tools(registry, repository)

    result = await registry.execute(
        "open_website", {"url": "file:///C:/Windows/win.ini"}, _deny_confirmation
    )

    assert result.status is ToolStatus.VALIDATION_FAILURE
    assert json.loads(result.content)["error"]["message"] == (
        "Invalid tool arguments."
    )


@pytest.mark.asyncio
async def test_confirmation_prevents_memory_write(repository) -> None:
    registry = ToolRegistry()
    register_builtin_tools(registry, repository)

    result = await registry.execute(
        "save_memory", {"content": "should not persist"}, _deny_confirmation
    )

    assert result.status is ToolStatus.DENIED
    assert repository.search_memories("should not persist") == []


@pytest.mark.asyncio
async def test_async_approval_denial_does_not_run_high_risk_tool() -> None:
    class EmptyArguments(BaseModel):
        pass

    handler_calls = []
    registry = ToolRegistry()
    registry.register(
        ToolDefinition(
            name="high-risk",
            description="An async-approval test.",
            arguments_model=EmptyArguments,
            handler=lambda _: handler_calls.append(True),
            risk=ToolRisk.HIGH,
            approval_policy=ApprovalPolicy.ALWAYS,
        )
    )

    async def deny(_):
        return False

    result = await registry.execute("high-risk", {}, deny)

    assert result.status is ToolStatus.DENIED
    assert handler_calls == []


@pytest.mark.asyncio
async def test_missing_or_indeterminate_approval_fails_closed() -> None:
    class EmptyArguments(BaseModel):
        pass

    handler_calls = []
    registry = ToolRegistry()
    registry.register(
        ToolDefinition(
            name="high-risk",
            description="A fail-closed approval test.",
            arguments_model=EmptyArguments,
            handler=lambda _: handler_calls.append(True),
            risk=ToolRisk.HIGH,
            approval_policy=ApprovalPolicy.ALWAYS,
        )
    )

    missing = await registry.execute("high-risk", {})

    async def no_decision(_):
        return None

    indeterminate = await registry.execute("high-risk", {}, no_decision)

    assert missing.status is ToolStatus.DENIED
    assert indeterminate.status is ToolStatus.DENIED
    assert handler_calls == []


@pytest.mark.asyncio
async def test_async_approval_exception_fails_closed() -> None:
    class EmptyArguments(BaseModel):
        pass

    handler_calls = []
    registry = ToolRegistry()
    registry.register(
        ToolDefinition(
            name="high-risk",
            description="An approval-error test.",
            arguments_model=EmptyArguments,
            handler=lambda _: handler_calls.append(True),
            risk=ToolRisk.HIGH,
            approval_policy=ApprovalPolicy.ALWAYS,
        )
    )

    async def fail(_):
        raise RuntimeError("decision service unavailable")

    result = await registry.execute("high-risk", {}, fail)

    assert result.status is ToolStatus.EXECUTION_FAILURE
    assert "tool was not executed" in json.loads(result.content)["error"]
    assert handler_calls == []


@pytest.mark.asyncio
async def test_async_approval_timeout_does_not_run_action(monkeypatch) -> None:
    class EmptyArguments(BaseModel):
        pass

    monkeypatch.setattr(registry_module, "MAX_APPROVAL_WAIT_SECONDS", 0.01)
    decision_ready = asyncio.Event()
    handler_calls = []
    registry = ToolRegistry()
    registry.register(
        ToolDefinition(
            name="high-risk",
            description="An approval-timeout test.",
            arguments_model=EmptyArguments,
            handler=lambda _: handler_calls.append(True),
            risk=ToolRisk.HIGH,
            approval_policy=ApprovalPolicy.ALWAYS,
        )
    )

    async def wait_for_decision(_):
        await decision_ready.wait()
        return True

    result = await registry.execute("high-risk", {}, wait_for_decision)

    assert result.status is ToolStatus.DENIED
    assert handler_calls == []
    decision_ready.set()
    await asyncio.sleep(0)


def test_builtin_tools_declare_risk_and_approval_policies(repository) -> None:
    registry = ToolRegistry()
    register_builtin_tools(registry, repository)

    assert registry._tools
    assert all(
        isinstance(tool.risk, ToolRisk)
        and isinstance(tool.approval_policy, ApprovalPolicy)
        for tool in registry._tools.values()
    )
    for tool_name in ("save_memory", "update_memory", "delete_memory"):
        assert registry._tools[tool_name].risk is ToolRisk.HIGH
        assert (
            registry._tools[tool_name].approval_policy
            is ApprovalPolicy.ALWAYS
        )


@pytest.mark.asyncio
async def test_memory_tools_create_update_and_delete_with_confirmation(
    repository,
) -> None:
    registry = ToolRegistry()
    register_builtin_tools(registry, repository)
    approvals = []

    def approve(request):
        approvals.append(request)
        return True

    created = await registry.execute(
        "save_memory",
        {
            "content": "Prefers concise emails",
            "category": "user_preference",
            "tags": ["email"],
        },
        approve,
    )
    assert created.status is ToolStatus.SUCCEEDED
    memory = json.loads(created.content)["result"]
    memory_id = memory["id"]
    updated = await registry.execute(
        "update_memory",
        {"memory_id": memory_id, "content": "Prefers concise work emails"},
        approve,
    )
    assert json.loads(updated.content)["result"]["content"] == (
        "Prefers concise work emails"
    )
    deleted = await registry.execute(
        "delete_memory", {"memory_id": memory_id}, approve
    )

    assert json.loads(deleted.content)["result"]["deleted"] is True
    assert [request.tool_name for request in approvals] == [
        "save_memory", "update_memory", "delete_memory"
    ]
    assert all(request.risk is ToolRisk.HIGH for request in approvals)
    assert json.loads(approvals[0].arguments_json)["content"] == (
        "Prefers concise emails"
    )
    assert repository.get_memory(memory_id) is None


@pytest.mark.asyncio
async def test_invalid_memory_is_reported_as_json(repository) -> None:
    registry = ToolRegistry()
    register_builtin_tools(registry, repository)

    result = await registry.execute(
        "save_memory", {"content": "   "}, _deny_confirmation
    )

    assert result.status is ToolStatus.VALIDATION_FAILURE
    assert json.loads(result.content)["error"]["message"] == (
        "Invalid tool arguments."
    )


@pytest.mark.asyncio
async def test_memory_write_database_failure_is_reported(repository, monkeypatch) -> None:
    def fail_connection():
        raise RuntimeError("database is locked")

    monkeypatch.setattr(repository.database, "connection", fail_connection)
    registry = ToolRegistry()
    register_builtin_tools(registry, repository)

    result = await registry.execute(
        "save_memory",
        {"content": "A test preference", "category": "user_preference"},
        lambda _: True,
    )

    assert result.status is ToolStatus.EXECUTION_FAILURE
    assert "database is locked" in json.loads(result.content)["error"]


@pytest.mark.asyncio
async def test_tool_failure_logs_do_not_include_exception_contents(
    caplog,
) -> None:
    class EmptyArguments(BaseModel):
        pass

    secret_text = "private-memory-content-should-not-be-logged"

    def fail(_: BaseModel) -> None:
        raise RuntimeError(secret_text)

    registry = ToolRegistry()
    registry.register(
        ToolDefinition(
            name="private-failure",
            description="A logging privacy test.",
            arguments_model=EmptyArguments,
            handler=fail,
            risk=ToolRisk.READ_ONLY,
            approval_policy=ApprovalPolicy.NEVER,
        )
    )

    result = await registry.execute("private-failure", {})

    assert result.status is ToolStatus.EXECUTION_FAILURE
    assert secret_text in json.loads(result.content)["error"]
    assert secret_text not in caplog.text


@pytest.mark.asyncio
async def test_invalid_memory_category_does_not_save(repository) -> None:
    registry = ToolRegistry()
    register_builtin_tools(registry, repository)

    result = await registry.execute(
        "save_memory",
        {"content": "A test preference", "category": "medical_record"},
        lambda _: True,
    )

    assert result.status is ToolStatus.VALIDATION_FAILURE
    assert repository.list_memories() == []


@pytest.mark.asyncio
async def test_website_is_opened_only_after_approval(
    repository, monkeypatch
) -> None:
    opened_urls = []
    monkeypatch.setattr(
        "kai.tools.builtin.webbrowser.open",
        lambda url, new: opened_urls.append((url, new)) or True,
    )
    registry = ToolRegistry()
    register_builtin_tools(registry, repository)

    result = await registry.execute(
        "open_website",
        {"url": "https://example.com"},
        lambda _: True,
    )

    assert result.status is ToolStatus.SUCCEEDED
    assert json.loads(result.content)["result"]["opened"] is True
    assert opened_urls == [("https://example.com/", 2)]


@pytest.mark.asyncio
async def test_unregistered_tool_is_rejected() -> None:
    result = await ToolRegistry().execute(
        "run_shell", {"command": "whoami"}, _deny_confirmation
    )

    assert result.status is ToolStatus.VALIDATION_FAILURE
    assert "Unknown tool" in json.loads(result.content)["error"]


def test_duplicate_registration_is_rejected() -> None:
    class EmptyArguments(BaseModel):
        pass

    registry = ToolRegistry()
    definition = ToolDefinition(
        name="sample",
        description="A test tool.",
        arguments_model=EmptyArguments,
        handler=lambda _: {"ok": True},
        risk=ToolRisk.READ_ONLY,
        approval_policy=ApprovalPolicy.NEVER,
    )
    registry.register(definition)

    try:
        registry.register(definition)
    except ValueError as exc:
        assert "already registered" in str(exc)
    else:
        raise AssertionError("Duplicate tool registration should fail.")


@pytest.mark.asyncio
async def test_approval_is_bound_to_canonical_validated_arguments() -> None:
    class Arguments(BaseModel):
        target: str

    received_arguments = []
    approval_requests = []
    registry = ToolRegistry()
    registry.register(
        ToolDefinition(
            name="change_target",
            description="A test action.",
            arguments_model=Arguments,
            handler=lambda args: received_arguments.append(args.target)
            or {"changed": args.target},
            risk=ToolRisk.MODERATE,
            approval_policy=ApprovalPolicy.ALWAYS,
        )
    )

    def approve(request):
        approval_requests.append(request)
        return True

    result = await registry.execute(
        "change_target", {"target": "folder/item.txt"}, approve
    )

    assert result.status is ToolStatus.SUCCEEDED
    assert approval_requests[0].tool_name == "change_target"
    assert approval_requests[0].risk is ToolRisk.MODERATE
    assert approval_requests[0].arguments_json == (
        '{"target":"folder/item.txt"}'
    )
    assert received_arguments == ["folder/item.txt"]


def test_high_risk_tool_cannot_skip_approval() -> None:
    class EmptyArguments(BaseModel):
        pass

    with pytest.raises(ValueError, match="must always require approval"):
        ToolDefinition(
            name="unsafe",
            description="An invalid high-risk tool.",
            arguments_model=EmptyArguments,
            handler=lambda _: None,
            risk=ToolRisk.HIGH,
            approval_policy=ApprovalPolicy.NEVER,
        )


def test_tool_risk_and_approval_policy_must_be_explicit_enums() -> None:
    class EmptyArguments(BaseModel):
        pass

    with pytest.raises(ValueError, match="valid risk classification"):
        ToolDefinition(
            name="bad-risk",
            description="Invalid risk metadata.",
            arguments_model=EmptyArguments,
            handler=lambda _: None,
            risk="high",
            approval_policy=ApprovalPolicy.ALWAYS,
        )

    with pytest.raises(ValueError, match="at most"):
        ToolDefinition(
            name="unbounded",
            description="Invalid execution deadline.",
            arguments_model=EmptyArguments,
            handler=lambda _: None,
            risk=ToolRisk.READ_ONLY,
            approval_policy=ApprovalPolicy.NEVER,
            timeout_seconds=float("inf"),
        )


@pytest.mark.asyncio
async def test_approval_callback_failure_does_not_run_tool() -> None:
    class EmptyArguments(BaseModel):
        pass

    handler_calls = []
    registry = ToolRegistry()
    registry.register(
        ToolDefinition(
            name="approved-action",
            description="An approval-gated test action.",
            arguments_model=EmptyArguments,
            handler=lambda _: handler_calls.append(True),
            risk=ToolRisk.MODERATE,
            approval_policy=ApprovalPolicy.ALWAYS,
        )
    )

    def approval_failure(_):
        raise RuntimeError("prompt unavailable")

    result = await registry.execute(
        "approved-action", {}, approval_failure
    )

    assert result.status is ToolStatus.EXECUTION_FAILURE
    assert "tool was not executed" in json.loads(result.content)["error"]
    assert handler_calls == []


@pytest.mark.asyncio
async def test_timed_out_sync_tool_reports_that_it_may_still_be_running() -> None:
    class EmptyArguments(BaseModel):
        pass

    started = threading.Event()
    release = threading.Event()
    finished = threading.Event()

    def slow_handler(_: BaseModel) -> dict[str, bool]:
        started.set()
        release.wait()
        finished.set()
        return {"finished": True}

    registry = ToolRegistry()
    registry.register(
        ToolDefinition(
            name="slow",
            description="A deliberately slow test action.",
            arguments_model=EmptyArguments,
            handler=slow_handler,
            risk=ToolRisk.READ_ONLY,
            approval_policy=ApprovalPolicy.NEVER,
            timeout_seconds=0.05,
        )
    )

    execution_task = asyncio.create_task(
        registry.execute("slow", {}, _deny_confirmation)
    )
    try:
        assert await asyncio.to_thread(started.wait, 1)
        result = await execution_task

        assert result.status is ToolStatus.TIMEOUT
        assert result.operation_may_still_be_running
        assert json.loads(result.content)["operation_may_still_be_running"] is True
        assert not finished.is_set()
    finally:
        release.set()
    assert await asyncio.to_thread(finished.wait, 1)


@pytest.mark.asyncio
async def test_timed_out_async_handler_may_continue_until_it_finishes() -> None:
    class EmptyArguments(BaseModel):
        pass

    started = asyncio.Event()
    release = asyncio.Event()
    finished = asyncio.Event()

    async def slow_handler(_: BaseModel) -> dict[str, bool]:
        started.set()
        await release.wait()
        finished.set()
        return {"finished": True}

    registry = ToolRegistry()
    registry.register(
        ToolDefinition(
            name="async-slow",
            description="A deliberately slow async test action.",
            arguments_model=EmptyArguments,
            handler=slow_handler,
            risk=ToolRisk.READ_ONLY,
            approval_policy=ApprovalPolicy.NEVER,
            timeout_seconds=0.02,
        )
    )

    result = await registry.execute("async-slow", {})

    assert started.is_set()
    assert result.status is ToolStatus.TIMEOUT
    assert result.operation_may_still_be_running
    assert not finished.is_set()
    release.set()
    await asyncio.wait_for(finished.wait(), timeout=1)
    await asyncio.sleep(0)


@pytest.mark.asyncio
async def test_cancelled_async_handler_returns_execution_failure() -> None:
    class EmptyArguments(BaseModel):
        pass

    async def cancel_handler(_: BaseModel) -> None:
        raise asyncio.CancelledError

    registry = ToolRegistry()
    registry.register(
        ToolDefinition(
            name="cancelled",
            description="A cancellation-result test.",
            arguments_model=EmptyArguments,
            handler=cancel_handler,
            risk=ToolRisk.READ_ONLY,
            approval_policy=ApprovalPolicy.NEVER,
        )
    )

    result = await registry.execute("cancelled", {})

    assert result.status is ToolStatus.EXECUTION_FAILURE
    assert result.operation_may_still_be_running


@pytest.mark.asyncio
async def test_retry_after_timeout_requires_a_fresh_approval() -> None:
    class Arguments(BaseModel):
        target: str

    started = threading.Event()
    release = threading.Event()
    finished = threading.Event()
    invocations = []
    approvals = []

    def slow_handler(arguments: Arguments) -> dict[str, str]:
        invocations.append(arguments.target)
        started.set()
        release.wait()
        finished.set()
        return {"target": arguments.target}

    def confirm(request):
        approvals.append(request.arguments_json)
        return len(approvals) == 1

    registry = ToolRegistry()
    registry.register(
        ToolDefinition(
            name="change-target",
            description="A timeout retry test.",
            arguments_model=Arguments,
            handler=slow_handler,
            risk=ToolRisk.MODERATE,
            approval_policy=ApprovalPolicy.ALWAYS,
            timeout_seconds=0.02,
        )
    )

    try:
        first = await registry.execute(
            "change-target", {"target": "report.txt"}, confirm
        )
        assert await asyncio.to_thread(started.wait, 1)
        second = await registry.execute(
            "change-target", {"target": "report.txt"}, confirm
        )

        assert first.status is ToolStatus.TIMEOUT
        assert first.operation_may_still_be_running
        assert second.status is ToolStatus.DENIED
        assert approvals == ['{"target":"report.txt"}'] * 2
        assert invocations == ["report.txt"]
    finally:
        release.set()
    assert await asyncio.to_thread(finished.wait, 1)
