# NexusAI — Principal Architecture Review
**Scope:** `app.py` (1,292 lines) · `index.html` · `style.css` · `app.js`  
**Reviewer Role:** Principal Software Architect — Chainlit / FastAPI / Async Python / Multi-modal AI  
**Severity Scale:** 🔴 P0 Critical Bug · 🟠 P1 High · 🟡 P2 Medium · 🔵 P3 Low / Style

---

## Executive Summary

NexusAI is architecturally ambitious and the dual-LLM fallback shim, the Gemini adapter wrappers, and the Shadow DOM injection strategy are all well-reasoned. However there are **3 Critical (P0)** bugs that will cause data loss or silent feature failure in production, **8 High (P1)** issues that block the async event loop or break layout, and several medium/low issues around API alignment and fragility. Every finding below is tied to a specific line range and includes a corrected code block.

---

## Part 1 — Database & Persistence Friction

### 🔴 P0-1 · `enforce_three_session_limit()` has no user scoping — deletes other users' threads

**Location:** `app.py:759-773`

The raw SQL query selects **all threads in the database**, not just the current user's. If User A starts their 4th chat while User B has sessions, the function will purge User B's oldest thread. In a multi-user deployment this is silent data destruction.

```python
# CURRENT (BROKEN)
result = await conn.execute(
    text("SELECT id FROM threads ORDER BY createdAt DESC")
)

# FIX — scope to the current user
user = cl.user_session.get("user")
if not user:
    return
result = await conn.execute(
    text("SELECT id FROM threads WHERE userId = :uid ORDER BY createdAt DESC"),
    {"uid": user.id}
)
```

Additionally, the `createdAt` column is typed as `String` (`Column("createdAt", String)`). Alphabetical ordering of ISO-8601 strings works *only* if all timestamps are zero-padded and in the same format. The moment any external code writes a non-padded timestamp, ordering breaks. Fix: use `CAST(createdAt AS DATETIME)` or store it as an epoch integer.

```python
# Robust ordering with String column
result = await conn.execute(
    text("SELECT id FROM threads WHERE userId = :uid ORDER BY datetime(createdAt) DESC"),
    {"uid": user.id}
)
```

---

### 🔴 P0-2 · `/new` factory reset drops the `users` table — logs out all users permanently

**Location:** `app.py:837-839`

```python
await conn.run_sync(metadata.drop_all)  # <-- drops users, threads, steps, elements, feedbacks
await conn.run_sync(metadata.create_all)
```

`metadata.drop_all` cascades through every table defined in the `metadata` object, including `users`. Every registered account is destroyed. A factory reset should only clear session history, not accounts.

```python
# FIX — selectively drop only session data tables
PURGEABLE_TABLES = [elements_table, feedbacks_table, steps_table, threads_table]
for table in PURGEABLE_TABLES:
    await conn.run_sync(lambda c, t=table: t.drop(c, checkfirst=True))
for table in reversed(PURGEABLE_TABLES):
    await conn.run_sync(lambda c, t=table: t.create(c, checkfirst=True))
```

---

### 🔴 P0-3 · `[FILE_SELECTED]` sent as `"system_message"` type — likely never triggers `@cl.on_message`

**Location:** `app.js:313-317`

```javascript
// CURRENT (BROKEN for triggering on_message)
window.sendChainlitMessage({
    type: "system_message",
    output: `[FILE_SELECTED:${file.name}]`
});
```

Chainlit's Copilot widget treats `system_message` type as a context injection that does **not** render in the UI and, critically, routes through a different internal handler than `on_message`. The `[FILE_SELECTED:]` and `[FILE_DESELECTED:]` intercepts in `handle_message` will silently never be reached. The file focus confirmation message the user sees from the Copilot will never appear.

```javascript
// FIX — use user_message type so on_message is triggered
window.sendChainlitMessage({
    type: "user_message",
    output: `[FILE_SELECTED:${file.name}]`
});
```

The backend's early-return guard already prevents these strings from leaking to the LLM, so visibility in the thread is not a problem.

---

### 🟠 P1-4 · SQLite foreign key constraints silently disabled — CASCADE deletes in the schema are fictional

**Location:** `app.py:113-191`

SQLite does not enforce `FOREIGN KEY` constraints unless you explicitly issue `PRAGMA foreign_keys = ON` per connection. Since you rely on manual cascade deletes in `enforce_three_session_limit`, this is survivable today — but the schema's `ondelete="CASCADE"` declarations give a false sense of safety and will silently do nothing if you ever rely on them.

Add this to `init_db()`:

```python
async def init_db():
    async with data_layer.engine.begin() as conn:
        await conn.execute(text("PRAGMA foreign_keys = ON"))
        await conn.run_sync(metadata.create_all)
```

Or configure it at engine level using SQLAlchemy's event system:

```python
from sqlalchemy import event

@event.listens_for(data_layer.engine.sync_engine, "connect")
def set_sqlite_pragma(dbapi_conn, connection_record):
    cursor = dbapi_conn.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()
```

---

### 🟡 P2-5 · `update_thread` overwrites existing metadata with `{}`

**Location:** `app.py:795`

```python
await cl_data._data_layer.update_thread(thread_id, name=title, metadata={})
```

This replaces the thread's stored metadata on every auto-rename call. If Chainlit internally stores session flags or profile data in thread metadata, they are silently erased after the first user message.

```python
# FIX — preserve existing metadata
existing_thread = await cl_data._data_layer.get_thread(thread_id)
existing_meta = existing_thread.metadata if existing_thread and existing_thread.metadata else {}
await cl_data._data_layer.update_thread(thread_id, name=title, metadata=existing_meta)
```

---

## Part 2 — Event Loop Blocking (Async Correctness)

All four of these issues occur in `async` functions. In Python's asyncio, a single synchronous blocking call inside a coroutine stalls the **entire event loop**, freezing all other concurrent WebSocket sessions until that call returns.

---

### 🟠 P1-6 · `auto_rename_session` makes a synchronous Groq network call

**Location:** `app.py:785-792`

```python
# CURRENT (BLOCKS event loop)
completion = groq_client.chat.completions.create(...)
```

```python
# FIX
import asyncio
loop = asyncio.get_running_loop()
completion = await loop.run_in_executor(
    None,
    lambda: groq_client.chat.completions.create(
        model="llama-3.1-8b-instant",
        messages=[
            {"role": "system", "content": "Summarize this into a 3-5 word title. No quotes. No extra text."},
            {"role": "user", "content": first_msg}
        ]
    )
)
```

---

### 🟠 P1-7 · Whisper transcription is a synchronous network call inside an async handler

**Location:** `app.py:724-727`

```python
# CURRENT (BLOCKS event loop)
transcription = groq_client.audio.transcriptions.create(
    model="whisper-large-v3",
    file=(filename, audio_data, mime_type)
)
```

```python
# FIX
loop = asyncio.get_running_loop()
transcription = await loop.run_in_executor(
    None,
    lambda: groq_client.audio.transcriptions.create(
        model="whisper-large-v3",
        file=(filename, audio_data, mime_type)
    )
)
```

Additionally, the MIME type extension extraction is fragile:
```python
# CURRENT — breaks for "audio/webm;codecs=opus" → produces "webm;codecs=opus"
buffer.name = f"input_audio.{mime_type.split('/')[1]}"

# FIX
clean_ext = mime_type.split('/')[1].split(';')[0]  # strips codec params
buffer.name = f"input_audio.{clean_ext}"
```

---

### 🟠 P1-8 · `/api/upload` uses synchronous file I/O in an async FastAPI endpoint

**Location:** `app.py:656-658`

```python
# CURRENT (BLOCKS event loop for large files)
with open(file_path, "wb") as buffer:
    shutil.copyfileobj(file.file, buffer)
```

```python
# FIX — use aiofiles (already imported)
import aiofiles

content = await file.read()
async with aiofiles.open(file_path, "wb") as f:
    await f.write(content)
```

---

### 🟠 P1-9 · `perform_web_search` (DDGS) is synchronous, called in async Steps

**Location:** `app.py:315-321`, called at `app.py:1091` and `app.py:1234`

```python
# CURRENT (BLOCKS event loop during web search)
def perform_web_search(query):
    results = DDGS().text(query, max_results=3)
    ...
```

```python
# FIX — wrap in executor at every call site
async def perform_web_search_async(query: str) -> str:
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, lambda: perform_web_search(query))

# In handle_message and action callbacks:
content = await perform_web_search_async(args.get("query"))
```

---

### 🟠 P1-10 · `build_vector_database()` blocks in `on_chat_end` and `/api/build-index`

**Locations:** `app.py:645`, `app.py:666`, `app.py:679`

```python
# FIX — run in executor
loop = asyncio.get_running_loop()
await loop.run_in_executor(None, build_vector_database)
```

---

## Part 3 — Chainlit API Alignment

### 🟠 P1-11 · Dual data layer registration — both `cl_data._data_layer` and `@cl.data_layer` used simultaneously

**Location:** `app.py:104-108`

```python
cl_data._data_layer = data_layer       # direct private assignment
cl_data._data_layer = data_layer

@cl.data_layer
def get_data_layer():
    return data_layer
```

You are registering the data layer twice using two different mechanisms. `cl_data._data_layer` is a private internal attribute. `@cl.data_layer` is the official public hook. Using both can lead to initialization order conflicts where Chainlit's startup routine overwrites your direct assignment. 

**Fix:** Remove the direct assignment and use only the decorator.

```python
# Remove this line entirely:
# cl_data._data_layer = data_layer

@cl.data_layer
def get_data_layer():
    return data_layer
```

Then update all direct references from `cl_data._data_layer` to `cl_data.get_data_layer()`:
```python
# Replace:
if not cl_data._data_layer or not hasattr(cl_data._data_layer, "engine"):
# With:
layer = cl_data.get_data_layer()
if not layer or not hasattr(layer, "engine"):
```

---

### 🟡 P2-12 · `cl.Text(name=src, path=src_path, display="side")` — `cl.Text` does not accept `path`

**Location:** `app.py:1085`

```python
elements.append(cl.Text(name=src, path=src_path, display="side"))
```

`cl.Text` accepts `name`, `content` (a string), `display`, and `language`. It does **not** accept a `path` parameter — that's `cl.File`. This call will either throw a Pydantic `ValidationError` or silently create an empty Text element.

```python
# FIX — read the file and pass content, or use cl.File
try:
    with open(src_path, "r", encoding="utf-8") as f:
        file_content = f.read()
    elements.append(cl.Text(name=src, content=file_content, display="side"))
except Exception:
    elements.append(cl.File(name=src, path=src_path, display="side"))
```

---

### 🟡 P2-13 · `@fastapi_app.on_event("startup")` is deprecated in FastAPI ≥ 0.93

**Location:** `app.py:197-199`

```python
@fastapi_app.on_event("startup")
async def startup_event():
    await init_db()
```

This emits a deprecation warning and will be removed in a future FastAPI release. Since you're mounting on Chainlit's FastAPI app, the lifespan approach requires hooking in carefully:

```python
# Safe approach that works with the existing Chainlit server
from fastapi import FastAPI
from contextlib import asynccontextmanager

# Register via startup handler at the app level (still works, raises no error currently)
# For future-proofing, add to app's router startup:
@fastapi_app.router.on_startup.append
async def startup_event():
    await init_db()
```

Or simply call `init_db()` at module load time inside an `asyncio.run()` wrapper to avoid the deprecated hook entirely.

---

### 🟡 P2-14 · Monkey patches are brittle — will silently break on Chainlit version upgrades

**Location:** `app.py:12-39`

The four monkey patches (`on_audio_chunk`, `on_audio_end`, `set_starters`, `set_chat_profiles`) exist to accommodate calling decorators both with and without `()`. This is a symptom of mixed calling styles in the codebase. Two of the usages are actually wrong:

- `@cl.set_starters()` — correct with `()`; remove monkey patch and call directly
- `@cl.set_chat_profiles()` — same
- `@cl.on_audio_chunk(name="audio-stream")` — `name` is not a valid parameter; simply use `@cl.on_audio_chunk` with no args
- `@cl.on_audio_end()` — empty `()` is unnecessary; use `@cl.on_audio_end`

**Fix:** Remove all four monkey patches. Correct the decorator call sites:

```python
# Remove the entire monkey-patch block (lines 12-39)

# Then fix decorators:
@cl.on_audio_chunk        # no args
async def on_audio_chunk(chunk): ...

@cl.on_audio_end          # no args  
async def on_audio_end(*args, **kwargs): ...

@cl.set_starters          # no parens needed — OR keep () which also works natively
async def set_starters(): ...

@cl.set_chat_profiles     # same
async def chat_profile(): ...
```

---

### 🔵 P3-15 · `sanitize_history_for_storage` is defined but never called

**Location:** `app.py:476-487`

This function strips image base64 blobs from history before saving to prevent bloated SQLite entries. It is well-written but dead code. It should be invoked when persisting:

```python
# In handle_message, before cl.user_session.set("message_history", history):
cl.user_session.set("message_history", sanitize_history_for_storage(history))
```

---

### 🟡 P2-16 · `DeepSearch` system injection appended to history on every message — grows unbounded

**Location:** `app.py:995-999`

```python
if deep_web:
    history.append({
        "role": "system",
        "content": "[SYSTEM INJECTION: Deep Web Search is enabled...]"
    })
```

This appends a new system message on **every user turn** when DeepSearch is on. After 10 messages, there are 10 copies of this injection in the history. Since history is also sent to the LLM on every call, token counts grow silently.

```python
# FIX — inject once, idempotently
DEEP_SEARCH_MARKER = "[SYSTEM INJECTION: Deep Web Search is enabled."
if deep_web:
    already_injected = any(
        msg.get("role") == "system" and DEEP_SEARCH_MARKER in msg.get("content", "")
        for msg in history
    )
    if not already_injected:
        history.append({"role": "system", "content": DEEP_SEARCH_MARKER + "...]"})
```

---

## Part 4 — DOM / Shadow DOM Conflict

### 🟠 P1-17 · CSS `!important` overrides in `style.css` targeting Shadow DOM elements are dead weight

**Location:** `style.css:152-212`

```css
#chainlit-copilot {
    display: block !important;  /* ← Has zero effect on Shadow DOM */
    ...
}
#chainlit-copilot-button { display: none !important; }   /* ← dead */
#chainlit-copilot-popover { display: block !important; } /* ← dead */
```

Shadow DOM is encapsulated by design. A stylesheet in the **Light DOM** (`style.css`) cannot reach elements inside a Shadow Root. These 60 lines of CSS are completely inert. The actual fix correctly lives in `app.js` where styles are injected directly into `copilotHost.shadowRoot`. The CSS block should be removed to avoid maintenance confusion.

**Keep only in `style.css`:**
```css
/* Only the container layout is in light DOM scope — these are valid */
.copilot-container, #copilot-root {
    height: 100vh;
    width: 30%;
    position: relative;
    background-color: var(--bg-color);
    border-left: 1px solid var(--border-color);
    box-sizing: border-box;
    overflow: hidden;
    /* Remove all !important flags — no shadow DOM can see them anyway */
}
```

---

### 🟡 P2-18 · `clearInterval` fires too early — interval clears before popover state is stable

**Location:** `app.js:69`

```javascript
clearInterval(openCopilotInterval);  // fires as soon as shadowRoot is found
```

The interval clears the moment `shadowRoot` is detected and styles are injected. However, Chainlit may toggle the popover's visibility using CSS **classes** (e.g., `hidden`, `visible`) rather than `style.display`. The check `popover.style.display === 'none'` only catches inline style changes and will miss class-based toggles, potentially leaving the panel closed.

```javascript
// FIX — check both style and class, then clear only after click or confirmed open state
const isHidden = !popover || 
    popover.style.display === 'none' || 
    popover.classList.contains('hidden') ||
    window.getComputedStyle(popover).display === 'none';

if (copilotBtn && isHidden) {
    copilotBtn.click();
}
clearInterval(openCopilotInterval);  // Clear after injection regardless — styles persist
```

---

### 🟡 P2-19 · `clear_visual_chat` DOM surgery on Copilot iframe will break on Chainlit UI updates

**Location:** `app.js:138-149`

```javascript
const containers = doc.querySelectorAll(
    '.step-container, [class*="step-container"], [class*="message-list"], .message-list'
);
```

This queries internal Chainlit React component class names that are not part of any public API. They will change without notice on Chainlit version upgrades. The feature will silently stop working. Since Chainlit exposes no public "clear" API, consider an alternative approach: instead of DOM surgery, trigger a `location.reload()` (like `/new-chat` does) or keep a running scroll offset and use CSS to hide messages above a certain scroll point.

---

## Part 5 — Multi-Modal & File Ingestion Pipeline

### 🟡 P2-20 · Large base64 images embedded in message strings risk hitting Chainlit/WS message size limits

**Location:** `app.js:468`, `app.py:915-923`

```javascript
// Can produce strings of 1-10+ MB for large images
promptText = `Please analyze this image: ${file.name}\n[IMAGE_DATA:${file.name}:${dataUrl}]`;
```

The regex on the backend uses `.*?` (non-greedy) matching over potentially megabytes of base64 data:
```python
pattern = r"\[IMAGE_DATA:(.*?):(data:image/.*?;base64,.*?)\]"
```

Non-greedy `.*?` on large strings causes extreme backtracking in the Python `re` engine. For a 5 MB image, this can take seconds and spike CPU.

**Better approach:** Upload the image via `/api/upload`, get a URL back, and pass just the URL to the Copilot instead of the raw base64 blob.

```javascript
// In analyzeStagedFiles(), for images:
const formData = new FormData();
formData.append('file', file);
const res = await fetch('/api/upload', { method: 'POST', body: formData });
const { filename } = await res.json();
promptText = `Please analyze the uploaded image: ${filename}`;
window.sendChainlitMessage({ type: "user_message", output: promptText });
```

On the backend, serve the image from `public/elements/` via FastAPI and build the image URL to pass to Groq/Gemini directly.

---

### 🟡 P2-21 · `[FILE_SELECTED:]` string parsing is fragile — breaks on filenames containing `]`

**Location:** `app.py:883`, `app.py:898`

```python
# CURRENT — fails for "report[final].pdf"
filename = message.content.split("[FILE_SELECTED:")[1].split("]")[0]
```

```python
# FIX — use regex
import re
match = re.search(r'\[FILE_SELECTED:(.*?)\]', message.content)
if match:
    filename = match.group(1)
else:
    return  # malformed message guard
```

---

### 🟡 P2-22 · `staging-tray` set to `display: block` — overrides flex layout

**Location:** `app.js:227`

```javascript
trayEl.style.display = 'block';  // breaks column layout of the tray
```

The `.staging-tray` in CSS is `display: flex; flex-direction: column`. Forcing `block` collapses the flex behavior, breaking the `tray-header` / `staged-files-list` vertical stack.

```javascript
trayEl.style.display = 'flex';  // restore correct flex layout
```

---

### 🔵 P3-23 · `/api/upload` has no path traversal sanitization

**Location:** `app.py:655`

```python
file_path = os.path.join(textbooks_dir, file.filename)
```

If a malicious client sends a filename like `../../app.py`, `os.path.join` will produce a path outside `textbooks_dir`. Sanitize:

```python
import pathlib

safe_name = pathlib.Path(file.filename).name  # strips any directory components
file_path = os.path.join(textbooks_dir, safe_name)
```

---

## Part 6 — Session State Isolation

### 🔵 P3-24 · `on_chat_end` deletes ALL textbooks — shared across users

**Location:** `app.py:633-646`

The `data/textbooks/` directory is shared on disk. When any user ends their session, all textbook files are deleted and the vector index is rebuilt empty. If two users are active simultaneously, User A's `on_chat_end` will delete User B's uploaded textbooks mid-session.

Fix: namespace the textbooks directory by user ID:
```python
user = cl.user_session.get("user")
user_dir = os.path.join(os.path.dirname(__file__), "data", "textbooks", user.id if user else "shared")
```

---

## Summary Table

| # | Severity | Location | Issue | Status |
|---|----------|----------|-------|--------|
| 1 | 🔴 P0 | `app.py:759` | `enforce_three_session_limit` deletes cross-user threads | Fix query to filter by `userId` |
| 2 | 🔴 P0 | `app.py:837` | `/new` drops `users` table, nukes all accounts | Selectively drop only session tables |
| 3 | 🔴 P0 | `app.js:314` | `FILE_SELECTED` as `system_message` never triggers `on_message` | Change to `user_message` |
| 4 | 🟠 P1 | `app.py:193` | SQLite FK constraints disabled — CASCADE is fictional | Add `PRAGMA foreign_keys = ON` |
| 5 | 🟡 P2 | `app.py:795` | `update_thread(metadata={})` erases existing metadata | Preserve existing meta |
| 6 | 🟠 P1 | `app.py:785` | Sync Groq call in `auto_rename_session` blocks event loop | Wrap in `run_in_executor` |
| 7 | 🟠 P1 | `app.py:724` | Sync Whisper transcription blocks event loop | Wrap in `run_in_executor` |
| 8 | 🟠 P1 | `app.py:656` | Sync file I/O in async `/api/upload` blocks event loop | Use `aiofiles` |
| 9 | 🟠 P1 | `app.py:315` | Sync DDGS `perform_web_search` blocks event loop | Wrap in `run_in_executor` |
| 10 | 🟠 P1 | `app.py:645` | Sync `build_vector_database()` in async handlers | Wrap in `run_in_executor` |
| 11 | 🟠 P1 | `app.py:104` | Dual data layer registration (`_data_layer` + `@cl.data_layer`) | Remove direct assignment |
| 12 | 🟡 P2 | `app.py:1085` | `cl.Text(path=...)` — Text has no `path` param → Pydantic error | Use `cl.File` or read content |
| 13 | 🟡 P2 | `app.py:197` | `@on_event("startup")` deprecated FastAPI pattern | Use router startup hook |
| 14 | 🟡 P2 | `app.py:12` | 4 monkey patches — fragile, breaks on Chainlit upgrades | Remove; fix decorator call sites |
| 15 | 🔵 P3 | `app.py:476` | `sanitize_history_for_storage` defined but never called | Call before session.set |
| 16 | 🟡 P2 | `app.py:996` | DeepSearch injection duplicates in history every message | Idempotent injection check |
| 17 | 🟠 P1 | `style.css:152` | Light DOM CSS overrides on Shadow DOM elements are dead | Remove; keep only container layout |
| 18 | 🟡 P2 | `app.js:65` | Interval clears before popover open state is confirmed | Check computed style + classes |
| 19 | 🟡 P2 | `app.js:138` | `clear_visual_chat` uses internal Chainlit class names | Fragile; document or replace |
| 20 | 🟡 P2 | `app.js:468` | Base64 images embedded in message strings risk size limits | Upload first, pass filename |
| 21 | 🟡 P2 | `app.py:883` | `[FILE_SELECTED:]` split parsing breaks on `]` in filename | Use regex |
| 22 | 🟡 P2 | `app.js:227` | `tray.display = 'block'` breaks flex tray layout | Change to `'flex'` |
| 23 | 🔵 P3 | `app.py:655` | No path traversal sanitization on upload filename | Use `pathlib.Path(name).name` |
| 24 | 🔵 P3 | `app.py:633` | `on_chat_end` deletes shared textbooks dir for all users | Namespace by user ID |

---

## Priority Fix Order

**Do immediately (P0 — production data risk):**
1. Scope `enforce_three_session_limit` SQL to current `userId`
2. Fix `/new` to not drop the `users` table
3. Change `FILE_SELECTED` to send as `user_message`

**Do before any multi-user load (P1 — event loop blockers):**
4. Wrap all 5 synchronous blocking calls in `run_in_executor`
5. Switch `/api/upload` to `aiofiles`
6. Remove the dual data layer registration
7. Remove the 60-line dead CSS block from `style.css`

**Clean up next (P2 — correctness & fragility):**
8. Fix `cl.Text(path=...)` → use `cl.File` or pass `content`
9. Fix DeepSearch injection deduplication
10. Fix staging tray `display: 'flex'`
11. Fix `update_thread(metadata={})` to preserve existing meta
12. Add PRAGMA for FK enforcement
13. Remove monkey patches; clean up decorator call sites
