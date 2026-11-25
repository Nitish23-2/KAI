import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    ollama_url: str = "http://localhost:11434"
    model: str = "qwen3:4b"
    database_path: Path = Path("data/kai.db")
    max_tool_rounds: int = 5
    request_timeout_seconds: float = 120.0
    context_size: int = 4096

    @classmethod
    def from_env(cls) -> "Settings":
        try:
            max_tool_rounds = int(os.getenv("KAI_MAX_TOOL_ROUNDS", "5"))
            request_timeout = float(
                os.getenv("KAI_REQUEST_TIMEOUT_SECONDS", "120")
            )
            context_size = int(os.getenv("KAI_CONTEXT_SIZE", "4096"))
        except ValueError as exc:
            raise ValueError(
                "KAI_MAX_TOOL_ROUNDS, KAI_REQUEST_TIMEOUT_SECONDS, and "
                "KAI_CONTEXT_SIZE must be numeric."
            ) from exc

        if not 1 <= max_tool_rounds <= 10:
            raise ValueError("KAI_MAX_TOOL_ROUNDS must be between 1 and 10.")
        if request_timeout <= 0:
            raise ValueError("KAI_REQUEST_TIMEOUT_SECONDS must be positive.")
        if not 512 <= context_size <= 32768:
            raise ValueError("KAI_CONTEXT_SIZE must be between 512 and 32768.")

        ollama_url = os.getenv(
            "KAI_OLLAMA_URL", "http://localhost:11434"
        ).rstrip("/")
        if not ollama_url.startswith(("http://", "https://")):
            raise ValueError("KAI_OLLAMA_URL must use HTTP or HTTPS.")

        model = os.getenv("KAI_MODEL", "qwen3:4b").strip()
        if not model:
            raise ValueError("KAI_MODEL cannot be empty.")

        return cls(
            ollama_url=ollama_url,
            model=model,
            database_path=Path(
                os.getenv("KAI_DATABASE_PATH", "data/kai.db")
            ).expanduser(),
            max_tool_rounds=max_tool_rounds,
            request_timeout_seconds=request_timeout,
            context_size=context_size,
        )
