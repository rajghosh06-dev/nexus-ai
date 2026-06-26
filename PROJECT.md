# Project: NexusAI UI & Features Overhaul

## Architecture
- **Frontend UI**: Chainlit-based interface, customized via `public/stylesheet.css` and `public/theme.json`. Supports Light/Dark modes, "Liquid Glass Frost" aesthetic (cyan-violet gradients, deep frost backgrounds, glass blur effects).
- **Backend API**: `app.py` serves the Chainlit application, routes LLM prompts using OpenAI/Gemini/Whisper, and integrates backend logic (RAG Search, network prediction, image description).
- **Database & Storage**: SQL database (`chainlit.db`) stores chat sessions, threads, steps, elements, and user information via `SQLAlchemyDataLayer`. Elements are stored locally via `LocalStorageClient` at `public/elements`.
- **Authentication**: Passwordless auth where username == password, managing session token and user profile context.

## Milestones
| # | Name | Scope | Dependencies | Status | Conv ID |
|---|---|---|---|---|---|
| 1 | E2E Testing Track | Implement E2E test runner and 4-tier test cases for all requirements (UI, Profiles, Settings, Starters, Actions, Ask User, Multi-modality, Auth, History) | None | IN_PROGRESS | ea78fd4b-352a-4cab-b610-2648d2205537 |
| 2 | UI & Light Mode Polish | Resolve light mode contrast, style settings screen with Liquid Glass Frost theme, ensure global aesthetic consistency | None | IN_PROGRESS | 7b16db2c-9f25-4bdd-b25c-e88e83d93b00 |
| 3 | Core Chainlit Features | Implement Chat Profiles, Chat Settings (Model, System Prompt), User Sessions & History, and verify Auth integration | M2 | PLANNED | 7b16db2c-9f25-4bdd-b25c-e88e83d93b00 |
| 4 | Advanced Interactive Features | Implement Starters, Ask User flow, Action buttons, and Multi-Modal input processing | M3 | PLANNED | 7b16db2c-9f25-4bdd-b25c-e88e83d93b00 |
| 5 | E2E Pass & Hardening | Run all tests (Tiers 1-4), perform Forensic Audit, and run adversarial testing (Tier 5) | M1, M4 | PLANNED | 7b16db2c-9f25-4bdd-b25c-e88e83d93b00 |

## Interface Contracts
### Chat Settings & Profile States
- System instructions update dynamically based on the current profile:
  - `Omni Mode`: Standard assistant.
  - `Scholar Mode`: Academic RAG search.
  - `Gamer Mode`: Ping prediction context (asks for game name).
  - `Voice Mode`: Voice processing context.
- Settings:
  - Model selection (mapped to correct LLM endpoints).
  - System prompt (appended to system instructions).
  - Temperature & DeepSearch flags.

### Data Layer Interactions
- Thread persistence limits history to 3 active threads per user.
- SQL DB schema remains compatible with SQLite SQLAlchemy layer.

## Code Layout
- `app.py`: Main Chainlit entrypoint and backend routing.
- `public/stylesheet.css`: Custom styling overrides.
- `public/theme.json`: Custom color palettes, typography, and dark/light settings.
- `src/`: Backend logic modules (`latency_predictor.py`, `rag_scholar.py`).
