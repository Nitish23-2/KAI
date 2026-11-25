# KAI

KAI is a local-first personal AI assistant project. This first milestone provides
a terminal assistant connected to Ollama, a validated tool registry, and SQLite
storage for conversations and explicitly approved memories.

The model can request only registered tools. It cannot execute Python or
terminal commands. Browser opening and memory saving require confirmation in
the terminal.

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
- `/exit` or `/quit` exits cleanly.

See [ARCHITECTURE.md](ARCHITECTURE.md) for component boundaries and
[DEVELOPMENT_PLAN.md](DEVELOPMENT_PLAN.md) for the roadmap.

## Tests

```powershell
python -m pytest
```

The automated tests use fake Ollama responses and do not require a running
model or open a real browser. Live connectivity, model inference, and browser
launch should be verified manually as described in the setup guide.
