# KAI Architecture

## Phase 1 boundary

The first milestone is a local terminal application. It separates reasoning,
tool policy, persistence, and user interaction so later interfaces can reuse
the core without allowing the model to execute arbitrary code.

```text
Terminal CLI
    |
AssistantEngine ---- OllamaClient ---- Ollama HTTP API
    |
ToolRegistry ---- validated built-in tools ---- SQLite / system browser
    |
Conversation and memory repositories ---- SQLite
```

## Components

- `interfaces/cli.py`: prompts the user, confirms side effects, and handles
  reset and shutdown commands.
- `ai/ollama.py`: communicates with Ollama's native chat API, checks model
  availability, and translates network/model errors into actionable messages.
- `ai/engine.py`: stores messages, supplies the system policy and tool
  definitions, and bounds the number of tool-call rounds and calls per turn.
- `tools/registry.py`: allow-lists tools, derives JSON schemas from Pydantic
  models, validates arguments, and enforces confirmation requirements.
- `tools/builtin.py`: implements local time, website opening, and memory tools.
- `storage/database.py` and `storage/repository.py`: create the SQLite schema
  and persist conversations, messages, and memories.
- `config.py` and `logging_config.py`: validate environment configuration and
  emit structured logs.

## Safety and trust boundaries

The model can only select tools registered by application code. Every tool
argument is validated before its handler runs. The website tool accepts only
HTTP(S) URLs and asks the user before launching a browser; memory writes also
require explicit user confirmation. Website text is not fetched or injected
into the model in this milestone. Conversation and memory data remain local in
SQLite.

## Deliberately deferred

FastAPI, browser automation, email/calendar access, speech, scheduling, remote
access, and a frontend are not part of this terminal milestone. They will be
added behind explicit interfaces and permissions when their use cases are
implemented.
