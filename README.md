# KAI

KAI is a local-first personal AI assistant project. The v0.2 milestone adds
persistent conversation management and structured, searchable personal memory
to the Ollama-powered terminal assistant.

The model can request only registered tools. It cannot execute Python or
terminal commands. Every tool has a declared risk and approval policy.
Approval-gated actions display the validated arguments and risk in the
terminal. Browser opening and memory changes require confirmation.

## Requirements

- Python 3.11 or newer (Python 3.12+ is the preferred project target).
- Ollama installed and running locally.
- A model with Ollama tool-calling support. The default is `qwen3:4b`.

## Quick start (Windows PowerShell)

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
ollama pull qwen3:4b
kai
```

If `ollama` is not recognized by PowerShell, see
[docs/SETUP.md](docs/SETUP.md) for the per-user executable path.

If PowerShell blocks activation, run the executable directly instead:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\kai.exe
```

Copy `.env.example` to `.env` to keep a local reference for configuration.
KAI reads configuration from environment variables; it does not load `.env`
files automatically. See [docs/SETUP.md](docs/SETUP.md) for setting variables.

## Terminal commands

- `/help` shows available commands.
- `/reset` starts a new conversation; previous conversation records remain in
  SQLite.
- `/conversations` lists active conversations; `/conversations all` includes
  archived ones.
- `/resume <id>` resumes a listed conversation.
- `/title <title>` sets the current conversation title.
- `/archive [id]` archives a conversation; archiving the current one starts a
  fresh conversation.
- `/exit` or `/quit` exits cleanly.

KAI stores memories by category (preferences, profile, education/work,
projects, workflows, and explicit facts), detects exact normalized duplicates,
and retrieves a small set of relevant memories using SQLite FTS5. Memory
creation, updates, and deletion are approval-gated. KAI does not automatically
extract personal information from chats.

See [ARCHITECTURE.md](ARCHITECTURE.md) for schema and retrieval details,
[docs/SETUP.md](docs/SETUP.md) for manual checks, and
[DEVELOPMENT_PLAN.md](DEVELOPMENT_PLAN.md) for the roadmap.

Tool execution has bounded deadlines and standardized result statuses. If a
handler exceeds its deadline, KAI reports that it may still be running rather
than claiming it was cancelled. Approval must explicitly return `True` and is
requested again for each invocation. Browser and Windows automation are not
part of this milestone.

## Tests

```powershell
python -m pytest
```

The automated tests use fake Ollama responses and do not require a running
model or open a real browser. Live connectivity, model inference, and browser
launch should be verified manually as described in the setup guide.
