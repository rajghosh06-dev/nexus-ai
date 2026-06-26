# NexusAI — Setup & Configuration Guide

Step-by-step environment setup, configuration reference, and deployment guidance.

---

## Table of Contents

- [Prerequisites](#prerequisites)
- [Installation](#installation)
- [Environment Variables](#environment-variables)
- [Chainlit Configuration](#chainlit-configuration)
- [Running NexusAI](#running-nexusai)
- [Database Setup](#database-setup)
- [Troubleshooting](#troubleshooting)
- [Upgrading](#upgrading)

---

## Prerequisites

| Requirement | Version | Notes |
|-------------|---------|-------|
| Python | 3.10+ | 3.11 recommended |
| pip | 23+ | Comes with Python |
| Chainlit | 2.11.0+ | Auto-installed via requirements |
| FAISS | latest | CPU version sufficient |
| SQLite | 3.x | Bundled with Python |

### API Keys Required

| Service | Purpose | Get Key |
|---------|---------|---------|
| **Groq** | Primary LLM (Llama 3, Mixtral) | [console.groq.com](https://console.groq.com) |
| **Google Gemini** | Vision + Fallback LLM | [aistudio.google.com](https://aistudio.google.com) |

---

## Installation

### Step 1 — Clone the Repository

```bash
git clone https://github.com/yourusername/nexus-ai.git
cd nexus-ai
```

### Step 2 — Create a Virtual Environment

**Windows (PowerShell):**
```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
```

**Linux / macOS:**
```bash
python -m venv .venv
source .venv/bin/activate
```

### Step 3 — Install Dependencies

```bash
pip install -r requirements.txt
```

Key packages installed:
- `chainlit>=2.11.0` — Framework
- `openai` — Groq/OpenAI-compatible client
- `google-generativeai` — Gemini SDK
- `faiss-cpu` — Vector search
- `sentence-transformers` — Embedding model
- `duckduckgo-search` — Web search
- `sqlalchemy[asyncio]` — Database ORM
- `aiosqlite` — Async SQLite driver
- `aiofiles` — Async file I/O
- `python-dotenv` — Environment variable loader

---

## Environment Variables

Create a `.env` file in the project root:

```bash
cp .env.example .env
```

Edit `.env` with your values:

```dotenv
# ─── REQUIRED ──────────────────────────────────
# Groq API key — primary LLM provider (free tier available)
GROQ_API_KEY=gsk_xxxxxxxxxxxxxxxxxxxxxxxxxxxx

# Google Gemini API key — vision + fallback LLM
GEMINI_API_KEY=AIzaSy_xxxxxxxxxxxxxxxxxxxxxxxxxxxx

# ─── OPTIONAL ──────────────────────────────────
# Chainlit authentication secret — any random string
# (required for session signing in production)
CHAINLIT_AUTH_SECRET=your-super-secret-random-string-here

# Override LLM models (defaults shown)
GROQ_MODEL=llama-3.3-70b-versatile
GEMINI_MODEL=gemini-2.0-flash

# Database path override (defaults to .chainlit/nexus.db)
# DATABASE_URL=sqlite+aiosqlite:///.chainlit/nexus.db

# Embedding model for RAG (defaults to all-MiniLM-L6-v2)
# EMBEDDING_MODEL=all-MiniLM-L6-v2
```

### Generating a Secure Auth Secret

```python
python -c "import secrets; print(secrets.token_hex(32))"
```

---

## Chainlit Configuration

The `.chainlit/config.toml` file controls framework behavior. Key settings:

```toml
[project]
session_timeout = 3600         # Session kept alive 1 hour after disconnect
allow_origins = ["*"]          # CORS — restrict to your domain in production

[features]
unsafe_allow_html = true       # Required for rich welcome cards
latex = true                   # KaTeX math rendering
auto_tag_thread = true         # Tag threads with active chat profile
favorites = true               # Allow users to favorite threads
edit_message = true            # Allow editing sent messages
prompt_playground = false      # Disable LLM playground

[features.audio]
enabled = true
min_decibels = -45             # Silence threshold (adjust for noisy environments)
initial_silence_timeout = 3000 # ms before auto-cancel if no speech
silence_timeout = 1500         # ms of silence to end recording

[features.spontaneous_file_upload]
enabled = true
accept = ["*/*"]
max_files = 10
max_size_mb = 100

[UI]
name = "NexusAI"
default_theme = "dark"         # "dark" or "light"
layout = "wide"                # "default" or "wide"
cot = "tool_call"              # Chain-of-thought: "hidden" | "tool_call" | "full"
chat_settings_location = "sidebar"
custom_css = "/public/stylesheet.css"
custom_js = "/public/workspace/app.js"
theme_path = "/public/theme.json"

[data_persistence]
enabled = true                 # Enable SQLite persistence
```

---

## Running NexusAI

### Development Mode (with hot reload)

```bash
chainlit run app.py -w
```

- Hot reload on file changes
- Debug logging enabled
- Opens at `http://localhost:8000`

### Production Mode

```bash
chainlit run app.py --host 0.0.0.0 --port 8000
```

### Access Points

| URL | Description |
|-----|-------------|
| `http://localhost:8000` | Main Chainlit chat interface |
| `http://localhost:8000/public/workspace/index.html` | Document workspace (split panel) |
| `http://localhost:8000/public/login/index.html` | Custom login page |

---

## Database Setup

NexusAI uses **SQLite** via the Chainlit SQLAlchemy data layer. The database is created automatically on first run.

### Database Location

```
.chainlit/nexus.db
```

### Schema Tables

| Table | Purpose |
|-------|---------|
| `users` | User accounts (id, identifier, metadata) |
| `threads` | Chat session threads |
| `steps` | Individual messages and tool calls |
| `feedbacks` | User ratings (👍/👎) |
| `elements` | Attached files and media references |

### Migrations

The database applies incremental migrations automatically on startup. For example, if upgrading from a version without `feedbacks.threadId`, the column is added safely with:

```python
ALTER TABLE feedbacks ADD COLUMN "threadId" TEXT
```

This is a safe no-op if the column already exists.

### Purging All Data (Factory Reset)

Use the `/new` slash command in the UI, or manually:

```bash
rm .chainlit/nexus.db
rm -rf data/textbooks/
```

Restart the server to reinitialize.

---

## Troubleshooting

### ❌ "ModuleNotFoundError: No module named 'chainlit'"

You forgot to activate your virtual environment:
```bash
.venv\Scripts\Activate.ps1  # Windows
source .venv/bin/activate    # Linux/macOS
```

### ❌ "GROQ_API_KEY not found"

Your `.env` file is missing or misconfigured. Check:
```bash
python -c "from dotenv import load_dotenv; load_dotenv(); import os; print(os.getenv('GROQ_API_KEY'))"
```

### ❌ Copilot Widget Not Loading in Workspace

Ensure NexusAI is running at `http://localhost:8000` before opening the workspace page. The workspace fetches the copilot script from that origin.

### ❌ "FAISS index file not found" on startup

This is normal on first run — FAISS creates an empty index. Upload a document via the chat or workspace to populate it.

### ❌ SQLite "database is locked"

Another process is accessing the database. Stop all running instances of NexusAI and restart:
```bash
# Kill all chainlit processes
taskkill /F /IM python.exe  # Windows
```

### ❌ Voice input not working

1. Check microphone permissions in your browser (site settings)
2. Ensure `CHAINLIT_AUTH_SECRET` is set (required for session security in some browsers)
3. Try Chrome or Edge (Firefox may have WebSocket audio restrictions)

### ⚠️ Light mode text invisible

If text disappears in light mode, hard-refresh the browser (`Ctrl+Shift+R`) to clear the CSS cache.

---

## Upgrading

### Upgrading Chainlit

```bash
pip install --upgrade chainlit
```

After upgrading, always test these areas:
- Login and session persistence
- File upload and RAG indexing
- Voice recording
- Action buttons (payload format changed in v2.x)

### Upgrading NexusAI

```bash
git pull origin main
pip install -r requirements.txt --upgrade
chainlit run app.py -w
```

The database auto-migrates on startup — no manual schema changes required.

---

## Directory Permissions (Windows)

If you see permission errors writing to `data/textbooks/` or `.chainlit/`:

```powershell
# Grant full access to the project directory
icacls "e:\RAJ-WORK\PROJECT\nexus-ai" /grant "%USERNAME%:(OI)(CI)F" /T
```

---

## Performance Tuning

| Setting | Location | Recommendation |
|---------|----------|---------------|
| `GROQ_MODEL` | `.env` | `llama-3.3-70b-versatile` for best quality |
| `EMBEDDING_MODEL` | `.env` | `all-MiniLM-L6-v2` for speed, `all-mpnet-base-v2` for accuracy |
| `session_timeout` | `config.toml` | Increase to 7200 for long working sessions |
| `max_size_mb` | `config.toml` | Increase for large PDF uploads |
