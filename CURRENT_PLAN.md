
# MISSION: Full-Stack Architecture Refactor & UI Overhaul for NexusAI
**Role:** You are an elite Full-Stack AI Engineer and UX/UI Specialist. You are an expert in FastAPI, Chainlit, and modern frontend web development.

## 1. Project Context & Current State
I am building "NexusAI", a dual-engine optimization environment (Scholar-Gamer CoPilot). The backend is driven by Groq and Gemini (via an Omni-Parser interceptor), routing queries between a RAG database, real-time ML predictors, and web search.

**The core issue:** The frontend layout is currently broken. Chainlit's injected React DOM / Shadow DOM for the Copilot widget is overriding the native CSS, resulting in a black screen that hides my custom HTML workspace layout. 

I need you to completely stabilize the UI, separate the interfaces, apply a specific visual theme, and enforce strict session management logic based on the official Chainlit documentation.

## 2. Directory Structure Context
Here is my exact, current working directory:
```text
NexusAI/
├── .chainlit/
│   └── config.toml
├── data/
│   ├── textbooks/
│   ├── raw_pings.csv
│   └── user_profile.json
├── models/
│   └── latency_model.pkl
├── public/
│   ├── workspace/
│   │   ├── index.html   (Custom Doc Viewer Frontend)
│   │   ├── style.css    (Currently broken/hidden by Chainlit)
│   │   └── app.js       (Widget mounter & File handler)
│   ├── favicon.ico
│   ├── logo_dark.png
│   ├── logo_light.png
│   ├── logo_transparent.png
│   ├── stylesheet.css   (Chainlit Main UI CSS)
│   └── theme.json
├── src/
│   ├── latency_predictor.py
│   ├── latency_tracker.py
│   ├── memory_manager.py
│   └── rag_scholar.py
├── vector_store/
│   └── faiss_index/
├── .env
├── .gitignore
└── app.py               (Main backend & routing engine)

```

## 3. Core Architectural Requirements

### A. The Dual Interface System

You must engineer the system to support two distinct user interfaces running concurrently from `app.py`:

1. **The Standard Interface (`http://localhost:8000/`):** The native Chainlit chat UI. This should be a clean, full-screen chat experience.
2. **The Document Analyzer (`http://localhost:8000/public/workspace/index.html`):** A custom HTML split-screen page. The left side must be a sleek "Dropzone" UI for uploading files. The right side must mount the `Chainlit Copilot` widget.
*CRITICAL FIX:* Ensure the CSS in `public/workspace/style.css` strictly sandboxes the Chainlit Copilot container to a 450px sidebar on the right, preventing it from turning the entire screen black or squishing the left workspace.

### B. "Liquid Glass Frost" UI Theme

I require a custom "Liquid Glass Frost" theme.

* It must apply to **both Light and Dark modes** independently.
* Use semi-transparent backgrounds, glassmorphism effects (backdrop-filter: blur), sleek cyan/neon blue accents, and a highly polished, premium aesthetic.
* Apply this theme via `.chainlit/config.toml`, `public/theme.json`, and `public/stylesheet.css`.

### C. Session Queue Management (Max 3)

* Update the session persistence logic (likely handled in `app.py` or `src/memory_manager.py`).
* The system must strictly maintain a maximum of **3 recent user sessions**.
* Implement a queue: When a 4th session is created, dequeue (delete) the oldest session so only the latest 3 are kept.
* Memory must stay entirely local.

### D. Security & Git Management

* Provide an updated `.gitignore` file.
* It MUST strictly ignore `.env`, the `data/` folder, the `vector_store/` folder, `__pycache__`, and any local SQLite/JSON user databases to protect user memory and API keys.

## 4. Chainlit Capabilities to Implement

I need you to heavily utilize Chainlit's advanced features in `app.py`. Review the following official documentation links to implement:

**Core Features & Integrations:**

* Standard Setup: https://docs.chainlit.io/get-started/overview
* FastAPI Integration: https://docs.chainlit.io/integrations/fastapi
* OpenAI/LLM Routing: https://docs.chainlit.io/integrations/openai
* Copilot Deployment: https://docs.chainlit.io/deploy/copilot
* Webapp Deployment: https://docs.chainlit.io/deploy/webapp

**UX & Lifecycle Elements:**

* Lifecycle: https://docs.chainlit.io/concepts/chat-lifecycle
* API Ref (on_chat_start, on_message, etc.): https://docs.chainlit.io/api-reference/lifecycle-hooks/on-chat-start
* Starters (Quick Actions): https://docs.chainlit.io/concepts/starters
* Loader Animations (Steps): https://docs.chainlit.io/concepts/step
* Slash Commands (`/`): https://docs.chainlit.io/concepts/command
* Sync/Async bridging: https://docs.chainlit.io/guides/sync-async

**Advanced UI & Persistence:**

* Chat Profiles (E.g., Scholar Mode vs Gamer Mode): https://docs.chainlit.io/advanced-features/chat-profiles
* Chat Settings (Input Widgets, Sliders): https://docs.chainlit.io/advanced-features/chat-settings
* Multimodal (Images/Files): https://docs.chainlit.io/advanced-features/multi-modal
* Ask User / Action buttons: https://docs.chainlit.io/advanced-features/ask-user
* History & Data Persistence: https://docs.chainlit.io/data-persistence/history
* User Sessions (Crucial for the 3-queue logic): https://docs.chainlit.io/concepts/user-session

**Customization:**

* UI Overhaul: https://docs.chainlit.io/customisation/overview
* Theme JSON: https://docs.chainlit.io/customisation/theme
* Examples Cookbook: https://docs.chainlit.io/examples/cookbook

## 5. Output Request

Please provide the complete, refactored code for the following files, ensuring all visual bugs are resolved and the Liquid Glass Frost theme is implemented:

1. `app.py` (Fully utilizing the API hooks, profiles, and commands).
2. `public/workspace/index.html`
3. `public/workspace/style.css` (Fixing the Copilot overlap bug).
4. `public/workspace/app.js`
5. `public/stylesheet.css` & `public/theme.json` (For the Liquid Glass theme).
6. `.gitignore`

Take a deep breath, analyze the DOM overlap issue for the Copilot, and output production-ready code.

