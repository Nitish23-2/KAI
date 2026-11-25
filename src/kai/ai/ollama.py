from typing import Any

import httpx
from pydantic import BaseModel, Field, ValidationError


class ToolFunction(BaseModel):
    name: str
    arguments: dict[str, Any]


class OllamaToolCall(BaseModel):
    id: str | None = None
    function: ToolFunction


class OllamaMessage(BaseModel):
    role: str
    content: str = ""
    thinking: str = ""
    tool_calls: list[OllamaToolCall] = Field(default_factory=list)


class OllamaChatResponse(BaseModel):
    message: OllamaMessage


class OllamaError(RuntimeError):
    """An actionable failure communicating with the local model."""


class OllamaClient:
    def __init__(
        self,
        base_url: str,
        model: str,
        timeout_seconds: float = 120,
        context_size: int = 4096,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.context_size = context_size
        self.transport = transport

    async def _request(
        self, method: str, path: str, **kwargs: Any
    ) -> dict[str, Any]:
        try:
            async with httpx.AsyncClient(
                timeout=self.timeout_seconds, transport=self.transport
            ) as client:
                response = await client.request(
                    method, f"{self.base_url}{path}", **kwargs
                )
                response.raise_for_status()
                result = response.json()
        except httpx.TimeoutException as exc:
            raise OllamaError(
                f"Ollama request timed out after {self.timeout_seconds:g}s. "
                "Check whether Ollama is running or increase "
                "KAI_REQUEST_TIMEOUT_SECONDS."
            ) from exc
        except httpx.HTTPStatusError as exc:
            detail = exc.response.text[:500]
            raise OllamaError(
                f"Ollama returned HTTP {exc.response.status_code}: {detail}"
            ) from exc
        except httpx.RequestError as exc:
            raise OllamaError(
                f"Could not connect to Ollama at {self.base_url}. "
                "Start Ollama and verify KAI_OLLAMA_URL."
            ) from exc
        except ValueError as exc:
            raise OllamaError("Ollama returned invalid JSON.") from exc
        if not isinstance(result, dict):
            raise OllamaError("Ollama returned an unexpected response shape.")
        return result

    async def list_models(self) -> list[str]:
        result = await self._request("GET", "/api/tags")
        models = result.get("models")
        if not isinstance(models, list):
            raise OllamaError("Ollama model-list response is malformed.")
        names = [
            item["name"]
            for item in models
            if isinstance(item, dict) and isinstance(item.get("name"), str)
        ]
        return names

    async def ensure_model_available(self) -> None:
        models = await self.list_models()
        if self.model not in models:
            raise OllamaError(
                f"Model '{self.model}' is not installed. Run "
                f"`ollama pull {self.model}` and try again."
            )

    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> OllamaMessage:
        result = await self._request(
            "POST",
            "/api/chat",
            json={
                "model": self.model,
                "messages": messages,
                "tools": tools,
                "stream": False,
                "think": False,
                "options": {
                    "num_ctx": self.context_size,
                    "num_predict": 512,
                },
            },
        )
        try:
            return OllamaChatResponse.model_validate(result).message
        except ValidationError as exc:
            raise OllamaError(
                "Ollama returned a malformed chat response."
            ) from exc
