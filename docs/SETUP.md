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
5. Explicitly ask KAI to remember a non-sensitive test preference, such as
   "Remember that I prefer concise email drafts." Review the proposed category,
   content, and source in the confirmation prompt and approve it.
6. Ask KAI to draft an email. Confirm the relevant saved preference is used.
   Ask "What do you remember about me?" and verify it reports the stored fact,
   not an invented one.
7. Ask KAI to update the preference. Approve the proposed update, then ask
   KAI to forget it and approve the deletion. Confirm it no longer appears in
   memory search.
8. Ask KAI to remember the same fact twice and verify no duplicate is created.
9. Enter `/conversations` and note an ID. Use `/resume <id>` to continue that
   thread; `/title <title>` sets its title. `/archive` archives the active
   conversation and starts a fresh one. `/conversations all` includes archives.
10. Ask "What did we discuss about [a topic from an earlier conversation]?"
    and verify KAI searches and retrieves the matching past discussion.
11. Exit and restart KAI. Verify the saved conversation list and unarchived
    messages remain available.
12. Try an invalid memory category or unknown tool and verify it is rejected.
    Enter `/reset` to start a new conversation and `/exit` to shut down.

The assistant stops after at most five tool-call rounds and ten individual
tool calls per user message. These defaults protect against runaway loops.

The model may not reliably choose a tool for every phrasing. If testing an
important workflow, phrase the request explicitly (for example, "What is the
current local date and time?").

Memory retrieval uses lexical FTS5 matching, not semantic embeddings. Use
distinctive topic words when asking about old conversations. If the SQLite
build has no FTS5, KAI uses a slower substring fallback. Conversation and
memory records are stored as plaintext in the local database; do not save
highly sensitive information.

## Verified on the development machine

On 2026-11-25, Ollama 0.40.18 and `qwen3:4b` (Q4_K_M, approximately 2.5 GB)
were confirmed installed and running. Live checks verified model connectivity,
a conversational response, date/time tool invocation, CLI startup/reset/exit,
and opening `https://example.com` in the system browser after approval.
Automated tests cover tool argument rejection, approval gating, memory
persistence across database reopen, v0.1 schema migration, relevant versus
unrelated retrieval, CRUD and duplicate handling, and model connection errors.

The v0.2 live check verified that Qwen3 saves an explicitly requested
`user_preference` after approval and that a later email request receives the
matching memory in its prompt. The CLI's conversation listing, resume, title,
and archive commands were exercised against a temporary database.

The Ollama executable is installed under the current user's
`%LOCALAPPDATA%\Programs\Ollama` directory but is not on PowerShell's PATH;
the application itself connects to Ollama through its local HTTP API, so this
does not prevent KAI from running.

The installed model reports thinking support as always enabled. KAI requests
no thinking output and limits generated tokens, but the model can still be slow
on CPU and may produce verbose self-talk; review its response rather than
assuming every generated answer is concise.
