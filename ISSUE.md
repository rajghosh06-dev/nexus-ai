# NexusAI — Issue Tracker

> Last Updated: 2026-06-26 | Status: ✅ Remediation Complete

---

## Priority Legend
- 🔴 **P0** — System-breaking / crashes
- 🟠 **P1** — Major feature broken
- 🟡 **P2** — Minor bug / suboptimal behavior
- 🔵 **P3** — Enhancement / polish
- ✅ **FIXED** | ⏭️ **N/A (Won't Fix)** | 🔍 **Monitoring**

---

## P0 — Critical (System Breaking)

| ID | Issue | Status | Resolution |
|----|-------|--------|------------|
| P0-3 | `system_message` type not triggering `on_message` | ⏭️ Downgraded to P2 | **Doc correction**: Chainlit's copilot docs confirm `system_message` type DOES arrive in `@cl.on_message` — it just doesn't render in UI. FILE_SELECTED uses `user_message` type which is correct. |

---

## P1 — Major Issues

| ID | Issue | Status | Resolution |
|----|-------|--------|------------|
| P1-1 | `feedbacks` table missing `threadId` column | ✅ FIXED | Added `Column("threadId", String, ForeignKey(...))` + incremental `ALTER TABLE` migration in `init_db()` |
| P1-2 | `elements.size` typed as `Integer` (Chainlit expects `String`) | ✅ FIXED | Changed to `Column("size", String)` |
| P1-3 | `steps` table had non-standard `icon` column | ✅ FIXED | Removed `Column("icon", String)` from `steps_table` |
| P1-4 | SQLite foreign key constraints not enforced | ✅ FIXED | Added `sa_event.listens_for(engine, "connect")` pragma + `init_db()` PRAGMA |
| P1-8 | Synchronous file I/O blocking async event loop | ✅ FIXED (prior) | Using `aiofiles` for all file operations |
| P1-9 | Synchronous web search blocking event loop | ✅ FIXED (prior) | Using `perform_web_search_async()` executor wrapper |
| P1-10 | Synchronous FAISS index rebuild blocking event loop | ✅ FIXED (prior) | `build_vector_database` runs in `loop.run_in_executor()` |

---

## P2 — Minor Issues

| ID | Issue | Status | Resolution |
|----|-------|--------|------------|
| P2-13 | `@fastapi_app.on_event("startup")` deprecated in FastAPI | ✅ FIXED | Replaced with `fastapi_app.router.on_startup.append(init_db)` |
| P2-14 | Audio chunk handler using monkey-patch | ✅ FIXED (prior) | Using `@cl.on_audio_chunk` decorator pattern |
| P2-15 | Session history not sanitized before storage | ✅ FIXED (prior) | `sanitize_history_for_storage()` called on all saves |
| P2-18 | Copilot Shadow DOM injection — fragile, version-tied | ✅ FIXED | Replaced with `displayMode: "sidebar"` (Chainlit v2.11+ native) |
| P2-19 | `clear_visual_chat` DOM surgery fragile | ✅ FIXED | Replaced with graceful no-op toast; visual clear via Chainlit new-chat |
| P2-20 | Large image base64 in WebSocket — size limit issue | ✅ FIXED (prior) | Images upload via `/api/upload` then referenced by server URL |
| P2-22 | `trayEl.style.display` wrong value (`'flex'` vs `'none'`) | ✅ FIXED (prior) | Using correct display values |
| P2-3 | `on_chat_resume` doesn't restore chat profile from thread metadata | ✅ FIXED | Reads `thread.metadata.chat_profile` on resume |
| P2-4 | `@cl.on_stop` hook missing — Stop button had no backend handler | ✅ FIXED | Added `@cl.on_stop` sets `should_stop = True`; streaming loops check and break |
| P2-5 | `@cl.on_logout` hook missing | ✅ FIXED | Added `@cl.on_logout` with cleanup logging |
| P2-6 | `@cl.author_rename` not implemented | ✅ FIXED | Added rename map: Chatbot→NexusAI, Tool→⚙️ NexusAI Tools |
| P2-7 | `cl.Action` using deprecated `value` parameter | ✅ FIXED | All `cl.Action()` calls now use `icon=` and no `value=` |
| P2-8 | `cl.ChatProfile` missing `starters` parameter | ✅ FIXED | Added 4 `cl.Starter` entries per profile |
| P2-9 | Modes API (`cl.Mode`, `cl.ModeOption`) not implemented | ✅ FIXED | Registered in `on_chat_start` and `on_chat_resume` |
| P2-10 | `config.toml` missing `layout`, `cot`, `chat_settings_location`, `favorites` | ✅ FIXED | Full config rewrite with all v2.11 fields |

---

## P3 — Enhancements / Polish

| ID | Issue | Status | Resolution |
|----|-------|--------|------------|
| P3-23 | Filename path traversal vulnerability in upload | ✅ FIXED (prior) | `pathlib.Path(filename).name` sanitizes filenames |
| P3-24 | Textbook files not namespaced by user | ✅ FIXED (prior) | Upload stores under `data/textbooks/{user_id}/` |
| P3-1 | Light mode UI — hardcoded dark `rgba()` values bleed through | ✅ FIXED | All stylesheet.css dark values replaced with CSS variable tokens |
| P3-2 | Workspace `style.css` — no light mode support, hardcoded dark | ✅ FIXED | Full CSS variable token system with dark/light variant overrides |
| P3-3 | `config.toml` `generated_by` still shows `1.3.0` | ✅ FIXED | Updated to `2.11.0` |

---

## Documentation

| ID | Issue | Status | Resolution |
|----|-------|--------|------------|
| D-1 | No README.md | ✅ FIXED | Created comprehensive [README.md](README.md) |
| D-2 | No GUIDE.md | ✅ FIXED | Created full feature [GUIDE.md](GUIDE.md) |
| D-3 | No SETUP.md | ✅ FIXED | Created installation/config [SETUP.md](SETUP.md) |

---

## Open / Monitoring

| ID | Issue | Status | Notes |
|----|-------|--------|-------|
| M-1 | `sendChainlitMessage` availability timing | 🔍 Monitoring | Sidebar mode loads faster but added null-check guard in app.js |
| M-2 | FAISS thread-safety in concurrent multi-user sessions | 🔍 Monitoring | Single-process SQLite + FAISS; scale with process-level locking if needed |
