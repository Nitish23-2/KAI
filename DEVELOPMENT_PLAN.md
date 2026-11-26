# Development Plan

## Phase 1: Local assistant foundation

- [x] Package configuration, environment settings, structured logging, and
  SQLite persistence.
- [x] Validated allow-listed tool registry and initial time, website, and memory
  tools.
- [x] Ollama chat integration with bounded tool execution.
- [x] Interactive terminal, conversation reset, and graceful exit.
- [x] Automated tests and setup documentation.
- [x] Install and verify Ollama plus the selected model on the development
  machine (Ollama 0.40.18, `qwen3:4b` Q4_K_M).
- [x] Verify live model conversation, date/time tool calling, CLI reset, and
  graceful exit.
- [x] Verify opening a website in the real system browser after user approval.

## Phase 2: Persistent intelligence and personal memory

- [x] Additive SQLite migration for conversation lifecycle and structured
  memories; preserve v0.1 records.
- [x] Conversation listing, timestamps, titles, archiving, resume, and ordered
  tool-call history.
- [x] Categorized memory CRUD, tags, provenance, duplicate detection, and
  approval-gated write tools.
- [x] FTS5 retrieval for relevant memories and historical conversations, with
  a SQLite fallback if FTS5 is unavailable.
- [x] Inject only relevant memories and bound recent model context for local
  inference.
- [x] Automated tests for persistence, migration, retrieval, CRUD, and model
  context.
- [x] Verify live explicit memory saving and subsequent relevant-memory
  injection with Qwen3.
- [x] Verify conversation listing, resume, title, and archive in the CLI.
- [x] Persist memory IDs supplied to each answer so KAI can explain prior
  memory context without resurrecting deleted records.

## Next phases

1. **Service boundary:** add FastAPI health/chat endpoints and a desktop-ready
   API only when a second interface needs them.
2. **v0.3 computer intelligence:** tool execution and permission contracts are
   complete in 0.3.1. Next implement allowlisted Windows app and scoped file
   operations (0.3.2), then isolated read-only Playwright browser tools (0.3.3).
   Browser and UI automation dependencies remain optional.
3. **Memory improvements:** evaluate richer multilingual/semantic retrieval
   only if lexical search is insufficient; keep automatic extraction opt-in.
4. **Computer automation:** add Playwright behind a constrained browser tool
   with explicit confirmation for submissions, downloads, and other impactful
   actions.
5. **Voice and proactive tasks:** evaluate CPU-friendly speech components and
   an opt-in scheduler after core interactions are dependable.
6. **Cross-device access:** define authentication and encrypted transport
   before exposing any service outside the local machine.
