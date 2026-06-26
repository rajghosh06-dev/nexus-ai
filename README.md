# ⚡ NexusAI

<div align="center">

**Dual-Engine Scholar-Gamer CoPilot**

*Powered by Groq · Gemini · Chainlit v2.11*

---

[![Chainlit](https://img.shields.io/badge/Chainlit-v2.11-00d4ff?style=flat-square)](https://chainlit.io)
[![Python](https://img.shields.io/badge/Python-3.10+-7c3aed?style=flat-square)](https://python.org)
[![License](https://img.shields.io/badge/License-MIT-10b981?style=flat-square)](LICENSE)

</div>

---

## What is NexusAI?

NexusAI is a **multi-modal AI assistant** that combines academic research, real-time web intelligence, and gaming network analytics into a single chat interface. It runs on your local machine using the Chainlit framework and connects to Groq and Google Gemini for ultra-fast inference.

### Four Operating Modes

| Mode | Icon | Specialization |
|------|------|----------------|
| **Omni Mode** | 🌐 | Full-capability: RAG + web + gaming |
| **Scholar Mode** | 📚 | Textbook RAG, academic research |
| **Gamer Mode** | 🎮 | Ping prediction, server status |
| **Voice Mode** | 🎙️ | Whisper speech-to-text transcription |

---

## Key Features

- 🔍 **Textbook RAG** — Upload PDFs, DOCX, code files and query them with vector search
- 🌐 **Live Web Search** — DuckDuckGo powered real-time intelligence
- 🎮 **Gaming Analytics** — Latency prediction, ping monitoring, server status
- 🖼️ **Vision Analysis** — Image understanding via Gemini Vision
- 🎙️ **Voice Input** — Whisper STT via Chainlit's native audio pipeline
- 💬 **Persistent Threads** — SQLite-backed conversation history with full resume
- 🎨 **Glassmorphism UI** — Full dark/light theme with animated glass effects
- 📁 **Native Workspace** — Split-panel document viewer with staging tray
- ⚡ **Slash Commands** — `/scholar`, `/gamer`, `/web`, `/clear`, `/reset-chat`, `/new-chat`
- 🎛️ **Modes Picker** — Per-message tool routing (Auto / Scholar / Gamer / Web)

---

## Architecture

```
nexus-ai/
├── app.py                    # Chainlit backend (all hooks, routes, tools)
├── .chainlit/config.toml     # Chainlit framework configuration
├── .env                      # API keys (not committed)
├── public/
│   ├── stylesheet.css        # Main Chainlit theme (glassmorphism)
│   ├── theme.json            # Color palette tokens
│   ├── workspace/
│   │   ├── index.html        # Workspace split-panel UI
│   │   ├── app.js            # Copilot integration + file handling
│   │   └── style.css         # Workspace panel CSS
│   └── login/
│       └── index.html        # Custom login page
├── src/
│   ├── rag_scholar.py        # FAISS vector DB + textbook search
│   └── latency_predictor.py  # Gaming latency ML model
├── data/textbooks/           # Uploaded documents for RAG indexing
├── .chainlit/
│   └── nexus.db              # SQLite persistence database
└── docs/
    ├── README.md             # This file
    ├── GUIDE.md              # Feature guide and usage examples
    └── SETUP.md              # Environment setup and configuration
```

---

## Quick Start

```bash
# 1. Clone the repository
git clone https://github.com/yourusername/nexus-ai.git
cd nexus-ai

# 2. Create and activate virtual environment
python -m venv .venv
.venv\Scripts\activate  # Windows
# source .venv/bin/activate  # Linux/Mac

# 3. Install dependencies
pip install -r requirements.txt

# 4. Configure API keys
cp .env.example .env
# Edit .env with your API keys

# 5. Run NexusAI
chainlit run app.py -w
```

Then open **http://localhost:8000** in your browser.

See [SETUP.md](SETUP.md) for full configuration instructions.

---

## Usage

1. **Login** — Use any username with the same string as your password (passwordless auth)
2. **Choose a Profile** — Select Scholar, Gamer, Omni, or Voice mode
3. **Chat** — Ask questions, use slash commands, or upload files
4. **Workspace** — Visit `/public/workspace/index.html` for the split-panel document workspace

See [GUIDE.md](GUIDE.md) for a complete feature walkthrough.

---

## License

MIT — see [LICENSE](LICENSE) for details.
