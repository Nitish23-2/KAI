# KAI Architecture

## Current boundary

KAI is a local terminal application. Reasoning, tool policy, persistence, and
user interaction stay in separate modules; the model cannot execute arbitrary
code.

```text
Terminal CLI
    |
AssistantEngine ---- OllamaClient ---- Ollama HTTP API
    |
ToolRegistry ---- validated tools ---- SQLite / system browser
    |
Repository ---- SQLite conversations, messages, memories, FTS5 indexes
```

## Components

- `interfaces/cli.py`: prompts the user, confirms side effects, and supports
  conversation listing, resume, title, archive, reset, and shutdown.
- `ai/ollama.py`: communicates with Ollama's native chat API, checks model
  availability, and translates network/model errors into actionable messages.
- `ai/engine.py`: supplies bounded recent history, relevant saved memories,
  system policy, and tool definitions; limits tool-call rounds and calls.
- `tools/registry.py`: allow-lists tools, derives JSON schemas from Pydantic
  models, validates arguments, and enforces confirmation requirements.
- `tools/builtin.py`: implements local time, website opening, structured memory
  operations, and historical conversation lookup.
- `storage/database.py` and `storage/repository.py`: create/migrate the SQLite
  schema and persist conversations, messages, and memories.
- `config.py` and `logging_config.py`: validate environment configuration and
  emit structured logs.

## Persistence schema

- `conversations`: UUID, title, creation/update timestamps, and optional archive
  timestamp.
- `messages`: ordered role/content rows with timestamps, serialized assistant
  tool calls, tool names, and matching tool-call IDs.
- `memories`: UUID, constrained category, content, normalized duplicate key,
  creation/update timestamps, JSON tags, and source/reason.
- `memory_fts` and `conversation_fts`: SQLite FTS5 indexes kept in sync by
  triggers. Memory duplicates are normalized by case and whitespace within a
  category. A duplicate save returns the existing record instead of inserting
  another.

Initialization applies additive column migrations and migrates v0.1 memories
into the structured table with the source `Migrated from KAI v0.1`. Existing
messages and conversation IDs are retained. If SQLite lacks FTS5, repository
search uses a bounded, parameterized substring fallback.

## Context and memory retrieval

Before each model call, the engine uses FTS5 lexical matching against the
current user message and injects at most five matching memories. Unrelated
memories are not included. Saved memory content is explicitly marked as data,
not instructions. There are no embeddings, external APIs, or vector database.
Only a bounded number of recent conversation turns are sent to the model;
complete history remains stored and can be retrieved through CLI or tools.
The IDs of memories supplied to a final response are persisted with that
assistant message. If asked how an earlier response was informed, the engine
loads those still-existing memory records; deleting a memory does not restore
its content. This records available context, not a provable causal explanation
of model behavior.

Memory categories are `user_preference`, `personal_profile`,
`education_work`, `project`, `workflow`, and `explicit_fact`. Create, update,
and delete tools require terminal approval. KAI must not infer or persist
personal details unless the user explicitly asks it to remember them.

## Safety and trust boundaries

The model can only select tools registered by application code. Every tool
argument is validated before its handler runs. The website tool accepts only
HTTP(S) URLs and asks the user before launching a browser; memory changes also
require explicit user confirmation. Historical messages, conversation search
results, tool outputs, and other external content are treated as untrusted data,
not instructions. Website text is not fetched or injected into the model.
Conversation and memory data remain in the local SQLite database (stored as
local plaintext).

## Deliberately deferred

FastAPI, browser automation expansion, email/calendar access, speech,
scheduling, remote access, and a frontend are deferred. They will be added
behind explicit interfaces and permissions when their use cases are
implemented.
