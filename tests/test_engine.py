import pytest

from kai.ai.engine import AssistantEngine
from kai.ai.ollama import OllamaError, OllamaMessage
from kai.tools.builtin import register_builtin_tools
from kai.tools.registry import ToolRegistry


class FakeOllamaClient:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.requests = []

    async def chat(self, messages, tools):
        self.requests.append((messages, tools))
        return next(self.responses)


@pytest.mark.asyncio
async def test_engine_executes_validated_tool_then_returns_answer(repository) -> None:
    conversation_id = repository.create_conversation()
    registry = ToolRegistry()
    register_builtin_tools(registry, repository)
    client = FakeOllamaClient(
        [
            OllamaMessage.model_validate(
                {
                    "role": "assistant",
                    "tool_calls": [
                        {
                            "id": "call-1",
                            "function": {
                                "name": "get_current_datetime",
                                "arguments": {},
                            },
                        }
                    ],
                }
            ),
            OllamaMessage(role="assistant", content="It is now."),
        ]
    )
    engine = AssistantEngine(client, registry, repository)

    response = await engine.respond(
        conversation_id, "What time is it?", lambda *_: False
    )

    assert response == "It is now."
    assert [message["role"] for message in repository.get_messages(conversation_id)] == [
        "user",
        "assistant",
        "tool",
        "assistant",
    ]


@pytest.mark.asyncio
async def test_engine_stops_at_tool_round_limit(repository) -> None:
    conversation_id = repository.create_conversation()
    registry = ToolRegistry()
    register_builtin_tools(registry, repository)
    call = OllamaMessage.model_validate(
        {
            "role": "assistant",
            "tool_calls": [
                {
                    "function": {
                        "name": "get_current_datetime",
                        "arguments": {},
                    }
                }
            ],
        }
    )
    client = FakeOllamaClient([call, call])
    engine = AssistantEngine(client, registry, repository, max_tool_rounds=1)

    with pytest.raises(OllamaError, match="tool-call limit"):
        await engine.respond(
            conversation_id, "Check the time.", lambda *_: False
        )


@pytest.mark.asyncio
async def test_engine_stops_when_single_response_exceeds_call_limit(
    repository,
) -> None:
    conversation_id = repository.create_conversation()
    registry = ToolRegistry()
    register_builtin_tools(registry, repository)
    call = {
        "function": {
            "name": "get_current_datetime",
            "arguments": {},
        }
    }
    response = OllamaMessage.model_validate(
        {"role": "assistant", "tool_calls": [call, call]}
    )
    client = FakeOllamaClient([response])
    engine = AssistantEngine(
        client, registry, repository, max_tool_rounds=5, max_tool_calls=1
    )

    with pytest.raises(OllamaError, match="1 calls per turn"):
        await engine.respond(
            conversation_id, "Check the time.", lambda *_: False
        )
    assert len(repository.get_messages(conversation_id)) == 1


@pytest.mark.asyncio
async def test_engine_rejects_empty_message(repository) -> None:
    client = FakeOllamaClient([])
    engine = AssistantEngine(client, ToolRegistry(), repository)
    conversation_id = repository.create_conversation()

    with pytest.raises(ValueError, match="1 to 10000"):
        await engine.respond(conversation_id, "  ", lambda *_: False)
