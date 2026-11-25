import json

import httpx
import pytest

from kai.ai.ollama import OllamaClient, OllamaError


@pytest.mark.asyncio
async def test_chat_parses_assistant_tool_call() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        assert payload["model"] == "qwen3:4b"
        assert payload["options"]["num_ctx"] == 4096
        assert payload["options"]["num_predict"] == 512
        assert payload["think"] is False
        return httpx.Response(
            200,
            json={
                "message": {
                    "role": "assistant",
                    "content": "",
                    "thinking": "private model reasoning",
                    "tool_calls": [
                        {
                            "function": {
                                "name": "get_current_datetime",
                                "arguments": {},
                            }
                        }
                    ],
                }
            },
        )

    client = OllamaClient(
        "http://ollama.test",
        "qwen3:4b",
        transport=httpx.MockTransport(handler),
    )

    message = await client.chat([], [])

    assert message.tool_calls[0].function.name == "get_current_datetime"
    assert message.thinking == "private model reasoning"


@pytest.mark.asyncio
async def test_connection_error_has_actionable_message() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("offline", request=request)

    client = OllamaClient(
        "http://ollama.test", "qwen3:4b", transport=httpx.MockTransport(handler)
    )

    with pytest.raises(OllamaError, match="Could not connect to Ollama"):
        await client.list_models()
