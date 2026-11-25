# Setup and Manual Verification

## Install

1. Install Python 3.11+ (3.12+ preferred) and Ollama for Windows.
2. In PowerShell, create and activate a virtual environment:

   ```powershell
   py -3.11 -m venv .venv
   .\.venv\Scripts\Activate.ps1
   python -m pip install -r requirements.txt
   ```

3. Start Ollama if its background service is not already running, then fetch
   the default model:

   ```powershell
   ollama pull qwen3:4b
   ollama list
   ```

   If `ollama` is not recognized in PowerShell, use the standard per-user
   install path directly:

   ```powershell
   $ollama = Join-Path $env:LOCALAPPDATA 'Programs\Ollama\ollama.exe'
   & $ollama pull qwen3:4b
   & $ollama list
   ```

4. Optional: copy `.env.example` to `.env` as a reference. Set overrides in
   the current PowerShell session, for example:

   ```powershell
   $env:KAI_MODEL = "qwen3:4b"
   $env:KAI_DATABASE_PATH = "data/kai.db"
   ```

   KAI intentionally reads process environment variables rather than silently
   parsing a `.env` file.

5. Start the assistant with `kai` (or `python -m kai`).

## Automated checks

Run `python -m pytest`. These tests use an in-memory HTTP mock or a fake
Ollama client; they do not call a live model or launch a browser.

## Manual checks

1. Confirm `ollama list` includes the configured model, then start `kai`.
   Startup checks Ollama connectivity and model availability and prints an
   actionable error if either check fails.
2. Ask a general question and verify the assistant replies.
3. Ask for the current time. Verify the tool execution is logged and a local
   time is returned.
4. Ask KAI to open a known `https://` site. Review the URL in the confirmation
   prompt and approve it; verify the system browser opens it. Decline once to
   confirm no browser launch occurs.
5. Explicitly ask KAI to remember a non-sensitive test fact. Review the
   confirmation prompt and approve. Search for the fact in the conversation.
   Exit, restart KAI, and search again to confirm SQLite persistence.
6. Try an invalid or unsupported request and verify it is reported without
   executing an unregistered tool.
7. Enter `/reset` to start a new conversation, then `/exit` to shut down.
   The prior conversation and memory should remain stored in `data/kai.db`.

The assistant stops after at most five tool-call rounds and ten individual
tool calls per user message. These defaults protect against runaway loops.

The model may not reliably choose a tool for every phrasing. If testing an
important workflow, phrase the request explicitly (for example, "What is the
current local date and time?").

## Verified on the development machine

On 2026-11-25, Ollama 0.40.18 and `qwen3:4b` (Q4_K_M, approximately 2.5 GB)
were confirmed installed and running. Live checks verified model connectivity,
a conversational response, date/time tool invocation, CLI startup/reset/exit,
and opening `https://example.com` in the system browser after approval.
Automated tests cover tool argument rejection, approval gating, memory
persistence across database reopen, and model connection errors.

The Ollama executable is installed under the current user's
`%LOCALAPPDATA%\Programs\Ollama` directory but is not on PowerShell's PATH;
the application itself connects to Ollama through its local HTTP API, so this
does not prevent KAI from running.
