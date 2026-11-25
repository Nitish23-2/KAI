# Changelog

## 0.2.0 - Persistent intelligence and personal memory

- Added backward-compatible SQLite migration, titled/archivable conversations,
  searchable history, resume support, and persisted tool-call IDs.
- Added categorized memories with UUIDs, timestamps, tags, provenance,
  duplicate detection, update/delete, and explicit confirmation.
- Added SQLite FTS5 retrieval for relevant memories and prior discussions, with
  a fallback for SQLite builds without FTS5.
- Added relevant-memory context and bounded recent history to model requests.
- Treat retrieved historical messages and tool results as untrusted data.
- Added CLI conversation listing, resume, title, and archive commands.
- Added migration, CRUD, relevance, continuity, and failure-path tests.
- Verified live Qwen3 memory saving/retrieval and CLI conversation management.

## 0.1.0 - Initial foundation

- Added a modular terminal assistant using Ollama's local chat API.
- Added bounded, schema-validated tool calls with confirmation for browser
  launches and memory writes.
- Added SQLite conversation and memory persistence.
- Added setup, architecture, development roadmap, and automated tests.
- Verified live Qwen3 conversation, date/time tool calling, CLI controls, and
  approval-gated browser opening with Ollama on Windows.
