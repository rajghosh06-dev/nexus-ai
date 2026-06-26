# NexusAI — Feature Guide

Complete usage reference for all NexusAI features.

---

## Table of Contents

- [Authentication](#authentication)
- [Chat Profiles / Modes](#chat-profiles--modes)
- [Slash Commands](#slash-commands)
- [Modes Picker](#modes-picker)
- [File Upload & RAG](#file-upload--rag)
- [Voice Mode](#voice-mode)
- [Document Workspace](#document-workspace)
- [Action Buttons](#action-buttons)
- [Chat History & Resume](#chat-history--resume)
- [Image Analysis](#image-analysis)
- [Keyboard Shortcuts](#keyboard-shortcuts)

---

## Authentication

NexusAI uses **passwordless authentication** — enter any username and use the same string as your password.

- First login creates your account automatically
- Your account is persisted in the SQLite database
- All threads are stored under your user identity

> **Example**: Username `raj`, Password `raj` → creates user `raj` with full thread history

---

## Chat Profiles / Modes

Select a profile when starting a new chat. Each profile pre-configures the AI's behavior and provides profile-specific **starter prompts**.

### 🌐 Omni Mode
Full-capability mode with access to all three tools:
- `query_academic_textbooks` — RAG search over uploaded PDFs
- `execute_web_search` — Live DuckDuckGo web search
- `check_game_network_stability` — Ping and latency analytics

**Best for**: General questions, mixed research, multi-tool tasks

### 📚 Scholar Mode
Optimized for academic research with textbook RAG prioritized.

**Best for**: Studying, homework, PDF analysis, academic topics

### 🎮 Gamer Mode
Specializes in gaming network analytics and server status.

**Best for**: Latency checks, ping prediction, finding best gaming hours, server outage info

### 🎙️ Voice Mode
Enables Whisper-powered speech transcription. Speak and the audio is transcribed before being processed by the AI.

**Best for**: Hands-free interaction, accessibility, audio file transcription

---

## Slash Commands

Type `/` in the chat input to activate the command picker.

| Command | Icon | Effect |
|---------|------|--------|
| `/scholar` | 📚 | Force textbook RAG lookup |
| `/gamer` | 🎮 | Force gaming latency analysis |
| `/web` | 🌐 | Force live web search |
| `/clear` | 🗑️ | Clear visual chat display (keeps memory) |
| `/reset-chat` | 🔄 | Wipe current thread's message history |
| `/new-chat` | ➕ | Start a new thread (max 3 simultaneous) |
| `/new` | ⚡ | Factory reset (wipes session data, keeps accounts) |

---

## Modes Picker

The **Modes Picker** appears in the message composer as a dropdown. It routes each individual message to a specific tool — more granular than slash commands.

| Mode | Routing |
|------|---------|
| **Auto** | AI decides which tool to use (default) |
| **Scholar** | Forces `query_academic_textbooks` tool |
| **Gamer** | Forces `check_game_network_stability` tool |
| **Web** | Forces `execute_web_search` tool |

> The Modes Picker supplements slash commands — if you've already used a slash command, that takes priority.

---

## File Upload & RAG

### Uploading via Chat

Use the 📎 attachment icon in the chat input to upload files directly into the conversation. Supported types:

- **Documents**: PDF, DOCX, TXT, MD, CSV
- **Code**: PY, JS, JSON, HTML, CSS
- **Images**: PNG, JPG, JPEG, WEBP
- **Spreadsheets**: XLS, XLSX
- **Presentations**: PPT, PPTX

### Using the Workspace Uploader

Visit `/public/workspace/index.html` to access the full document workspace with a staging tray and inline preview.

1. Drag files onto the drop zone or click to select
2. Files appear in the **staging tray** at the bottom
3. Click a file to **select** it (one file at a time)
   - Document files are uploaded to the neural index automatically
   - Image files are loaded into the viewer for preview
4. Click **"Analyze Selected File"** to send the file to the AI

### RAG Indexing

Uploaded documents are:
1. Parsed and chunked with sentence-aware splitting
2. Indexed in a FAISS vector database
3. Retrieved by cosine similarity on each Scholar query

Source pages are shown as **side elements** after scholar responses.

---

## Voice Mode

1. Switch to **Voice Mode** profile
2. Click the **🎙️ microphone** button in the chat input
3. Speak your query
4. NexusAI transcribes via Whisper and responds with text (+ TTS if enabled)

**Audio settings** (configurable in `.chainlit/config.toml`):
- `min_decibels`: Silence threshold (`-45` by default)
- `initial_silence_timeout`: 3 seconds before auto-cancel
- `silence_timeout`: 1.5 seconds of silence to end recording

---

## Document Workspace

The workspace (`/public/workspace/index.html`) provides a split-panel interface:

```
┌──────────────────────────────────┬─────────────┐
│                                  │             │
│    Document Viewer (80%)         │  Chainlit   │
│    PDF • Text • Image Preview    │  Sidebar    │
│                                  │             │
├──────────────────────────────────│             │
│  Drop Zone  │  Staging Tray      │             │
│             │  [file] [file]     │             │
└──────────────────────────────────┴─────────────┘
```

### Viewer Modes

| File Type | Preview |
|-----------|---------|
| PDF | Native iframe viewer |
| TXT, PY, JS, JSON, MD, CSV | Syntax-highlighted code view |
| PNG, JPG, JPEG, WEBP | Image preview |
| DOCX, XLS, PPTX, etc. | Loaded badge (analysis via AI) |

### Toast Notifications

The workspace shows contextual toasts for:
- ✅ Successful file staging / upload
- ⚠️ Warnings (e.g. one file already selected)
- ❌ Errors (invalid type, upload failure)

---

## Action Buttons

After each AI response, three action buttons appear:

| Button | Icon | Effect |
|--------|------|--------|
| **Regenerate** | 🔄 | Re-generate the last AI response |
| **Verify Citations** | 📄 | Shows the RAG source documents used |
| **Search Web** | 🌐 | Re-runs the last query with live web search |

You can **stop generation** at any time using the Stop button (⏹) in the message composer.

---

## Chat History & Resume

- All conversations are **automatically saved** as threads
- Thread list appears in the sidebar under **History**
- Click any past thread to **resume it** — full message history is restored
- Threads are tagged with your active chat profile
- Threads can be **favorited** (⭐) for quick access

---

## Image Analysis

NexusAI supports vision analysis via Gemini Vision:

1. Upload an image via the chat attachment icon, or via the workspace viewer
2. Ask: *"What is in this image?"* or *"Extract all text from this image."*
3. The AI uses Gemini Vision for multi-modal understanding

For large images (> 500KB), images are uploaded to the server first and referenced by URL to avoid WebSocket size limits.

---

## Keyboard Shortcuts

| Shortcut | Action |
|----------|--------|
| `Enter` | Send message |
| `Shift + Enter` | New line in message |
| `/` | Open slash command picker |
| `Esc` | Close any open modal |

---

## Tips & Tricks

- **Combine modes**: Use the Modes Picker set to "Scholar" with the Scholar Mode profile for maximum RAG accuracy
- **Multi-file context**: Upload multiple docs to the staging tray — all are indexed; select one to focus on
- **Chain queries**: The AI maintains full conversation history, so follow-up questions get full context
- **Reset vs Clear**: `/clear` only hides messages visually; `/reset-chat` wipes the LLM context window
