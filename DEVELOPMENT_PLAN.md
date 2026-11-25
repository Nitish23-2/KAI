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

## Next phases

1. **Service boundary:** add FastAPI health/chat endpoints and a desktop-ready
   API only when a second interface needs them.
2. **Reliable tool orchestration:** introduce per-tool permissions, timeouts,
   audit records, and safer approval UX as the tool set grows.
3. **Memory improvements:** add user-visible memory management, deletion,
   correction, and retrieval tests before any automatic memory extraction.
4. **Computer automation:** add Playwright behind a constrained browser tool
   with explicit confirmation for submissions, downloads, and other impactful
   actions.
5. **Voice and proactive tasks:** evaluate CPU-friendly speech components and
   an opt-in scheduler after core interactions are dependable.
6. **Cross-device access:** define authentication and encrypted transport
   before exposing any service outside the local machine.
