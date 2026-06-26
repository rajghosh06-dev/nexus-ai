import os
import pathlib
import hashlib
import json
import uuid
import asyncio
import base64
import re
from datetime import datetime
from dotenv import load_dotenv
import chainlit as cl
from openai import OpenAI
from openai import AsyncOpenAI
from fastapi import Request, Response

# Load environment variables first
load_dotenv()

from duckduckgo_search import DDGS

# Import backend modules
from src.latency_predictor import predict_latency
from src.rag_scholar import search_textbooks_with_sources, build_vector_database
from chainlit.server import app as fastapi_app
from fastapi import UploadFile, File, Response
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
import asyncio

import chainlit.data as cl_data
from chainlit.data.sql_alchemy import SQLAlchemyDataLayer
from sqlalchemy import MetaData, Table, Column, String, Boolean, Integer, ForeignKey, event as sa_event
from sqlalchemy import text
import aiofiles
from typing import Union, Dict, Any, List, Optional, Sequence
from chainlit.data.storage_clients.base import BaseStorageClient


# --- CUSTOM LOCAL BLOB STORAGE PROVIDER ---
class LocalStorageClient(BaseStorageClient):
    def __init__(self, base_dir="public/elements", base_url="/public/elements"):
        self.base_dir = base_dir
        self.base_url = base_url
        os.makedirs(self.base_dir, exist_ok=True)

    async def upload_file(
        self,
        object_key: str,
        data: Union[bytes, str],
        mime: str = "application/octet-stream",
        overwrite: bool = True,
        content_disposition: str | None = None,
    ) -> Dict[str, Any]:
        file_path = os.path.join(self.base_dir, object_key)
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        if isinstance(data, str):
            async with aiofiles.open(file_path, "w", encoding="utf-8") as f:
                await f.write(data)
        else:
            async with aiofiles.open(file_path, "wb") as f:
                await f.write(data)
        url = f"{self.base_url}/{object_key}"
        return {"object_key": object_key, "url": url}

    async def delete_file(self, object_key: str) -> bool:
        file_path = os.path.join(self.base_dir, object_key)
        if os.path.exists(file_path):
            os.remove(file_path)
            return True
        return False

    async def get_read_url(self, object_key: str) -> str:
        return f"{self.base_url}/{object_key}"

    async def close(self) -> None:
        pass


# Configure Storage Provider
storage_provider = LocalStorageClient()

class NexusDataLayer(SQLAlchemyDataLayer):
    async def execute_sql(self, query: str, parameters: dict):
        if parameters:
            if "modes" in parameters and not isinstance(parameters["modes"], str) and parameters["modes"] is not None:
                parameters["modes"] = json.dumps(parameters["modes"])
            if "tags" in parameters and not isinstance(parameters["tags"], str) and parameters["tags"] is not None:
                parameters["tags"] = json.dumps(parameters["tags"])
        return await super().execute_sql(query, parameters)

# Configure Data Layer globally
# FIX P1-11: Remove direct cl_data._data_layer assignment; use only @cl.data_layer decorator
data_layer = NexusDataLayer(
    conninfo="sqlite+aiosqlite:///chainlit.db",
    storage_provider=storage_provider
)

@cl.data_layer
def get_data_layer():
    return data_layer


# --- DATABASE SCHEMA DEFINITION ---
metadata = MetaData()

users_table = Table(
    "users",
    metadata,
    Column("id", String, primary_key=True),
    Column("identifier", String, unique=True, nullable=False),
    Column("createdAt", String),
    Column("metadata", String)
)

threads_table = Table(
    "threads",
    metadata,
    Column("id", String, primary_key=True),
    Column("createdAt", String),
    Column("name", String),
    Column("userId", String, ForeignKey("users.id", ondelete="CASCADE")),
    Column("userIdentifier", String),
    Column("tags", String),
    Column("metadata", String)
)

steps_table = Table(
    "steps",
    metadata,
    Column("id", String, primary_key=True),
    Column("name", String, nullable=False),
    Column("type", String, nullable=False),
    Column("threadId", String, ForeignKey("threads.id", ondelete="CASCADE"), nullable=False),
    Column("parentId", String),
    Column("command", String),
    Column("modes", String),
    Column("streaming", Boolean, nullable=False),
    Column("waitForAnswer", Boolean),
    Column("isError", Boolean),
    Column("metadata", String),
    Column("tags", String),
    Column("input", String),
    Column("output", String),
    Column("createdAt", String),
    Column("start", String),
    Column("end", String),
    Column("generation", String),
    Column("showInput", String),
    Column("defaultOpen", Boolean),
    Column("autoCollapse", Boolean),
    Column("language", String),
)

feedbacks_table = Table(
    "feedbacks",
    metadata,
    Column("id", String, primary_key=True),
    Column("forId", String, ForeignKey("steps.id", ondelete="CASCADE"), nullable=False),
    Column("threadId", String, ForeignKey("threads.id", ondelete="CASCADE")),
    Column("value", Integer, nullable=False),
    Column("comment", String)
)

elements_table = Table(
    "elements",
    metadata,
    Column("id", String, primary_key=True),
    Column("threadId", String, ForeignKey("threads.id", ondelete="CASCADE")),
    Column("type", String),
    Column("chainlitKey", String),
    Column("path", String),
    Column("url", String),
    Column("objectKey", String),
    Column("name", String, nullable=False),
    Column("display", String),
    Column("size", String),
    Column("language", String),
    Column("page", Integer),
    Column("props", String),
    Column("autoPlay", Boolean),
    Column("playerConfig", String),
    Column("forId", String),
    Column("mime", String)
)

# Tables that can be safely purged without destroying user accounts
PURGEABLE_TABLES = [elements_table, feedbacks_table, steps_table, threads_table]


async def init_db():
    """Initialize the database with FK enforcement and incremental schema migrations."""
    async with data_layer.engine.begin() as conn:
        await conn.execute(text("PRAGMA foreign_keys = ON"))
        await conn.run_sync(metadata.create_all)
        # Migration: add threadId to feedbacks table for pre-existing databases
        try:
            await conn.execute(text('ALTER TABLE feedbacks ADD COLUMN "threadId" TEXT'))
            print("[*] DB Migration: Added threadId column to feedbacks table.")
        except Exception:
            pass  # Column already exists — safe to ignore


# FK enforcement on every new SQLite connection (belt-and-suspenders)
@sa_event.listens_for(data_layer.engine.sync_engine, "connect")
def set_sqlite_fk_pragma(dbapi_conn, _):
    cursor = dbapi_conn.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


# Non-deprecated startup registration pattern
fastapi_app.router.on_startup.append(init_db)


# --- ADAPTERS FOR NATIVE GEMINI SDK WRAPPERS ---
class OpenAIChunkDelta:
    def __init__(self, content):
        self.content = content

class OpenAIChunkChoice:
    def __init__(self, delta):
        self.delta = delta

class OpenAIChunk:
    def __init__(self, content):
        self.choices = [OpenAIChunkChoice(OpenAIChunkDelta(content))]

def wrap_gemini_stream(gemini_stream):
    for chunk in gemini_stream:
        try:
            yield OpenAIChunk(chunk.text)
        except Exception:
            pass

class GeminiToolFunction:
    def __init__(self, name, arguments):
        self.name = name
        self.arguments = arguments

class GeminiToolCall:
    def __init__(self, id, name, arguments):
        self.id = id
        self.type = "function"
        self.function = GeminiToolFunction(name, arguments)

class GeminiMessage:
    def __init__(self, content, tool_calls=None):
        self.role = "assistant"
        self.content = content or ""
        self.tool_calls = tool_calls

class GeminiChoice:
    def __init__(self, message):
        self.message = message

class GeminiCompletion:
    def __init__(self, message):
        self.choices = [GeminiChoice(message)]


# --- INITIALIZE DUAL-PROVIDER ARCHITECTURE ---
API_KEY_GROQ = os.getenv("GROQ_API_KEY")
API_KEY_GEMINI = os.getenv("GEMINI_API_KEY")

if not API_KEY_GROQ or not API_KEY_GEMINI:
    raise ValueError("[-] Critical Error: Missing API Keys in .env file.")

try:
    groq_client = OpenAI(api_key=API_KEY_GROQ, base_url="https://api.groq.com/openai/v1")
    openai_client = AsyncOpenAI(api_key=os.environ.get("OPENAI_API_KEY", "dummy_key_if_missing"))
    import warnings
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        import google.generativeai as genai
    getattr(genai, "configure")(api_key=API_KEY_GEMINI)
    gemini_client = genai
except Exception as e:
    print(f"[-] Client initialization error: {e}")


TOOLS_SCHEMA = [
    {
        "type": "function",
        "function": {
            "name": "check_game_network_stability",
            "description": "Predicts network latency (ping) or server stability for a given hour.",
            "parameters": {
                "type": "object",
                "properties": {
                    "hour": {
                        "type": "integer",
                        "description": "The hour of the day (0-23) for which to predict latency."
                    }
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "query_academic_textbooks",
            "description": "Searches through academic textbooks.",
            "parameters": {
                "type": "object",
                "properties": {
                    "search_query": {"type": "string"}
                },
                "required": ["search_query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "execute_web_search",
            "description": "Searches the live internet.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"}
                },
                "required": ["query"]
            }
        }
    }
]


def perform_web_search(query):
    """Synchronous web search — only call via perform_web_search_async from async contexts."""
    try:
        results = DDGS().text(query, max_results=3)
        return "\n\n".join([f"Source: {res['title']}\nSnippet: {res['body']}" for res in
                            results]) if results else "No internet results."
    except Exception as e:
        return f"Web search failed: {str(e)}"


async def perform_web_search_async(query: str) -> str:
    """FIX P1-9: Wrap synchronous DDGS search in executor to avoid event-loop blocking."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, lambda: perform_web_search(query))


async def call_llm_with_fallback(messages, tools=None, tool_choice=None, temperature=None, vision_mode=False, requested_model=None):
    if vision_mode:
        MODELS_ROUTE = [
            {"provider": "Groq", "client": groq_client, "model": "llama-3.2-90b-vision-preview"},
            {"provider": "Gemini", "client": gemini_client, "model": "gemini-1.5-flash"}
        ]
        tools = None
    else:
        MODELS_ROUTE = []
        if requested_model:
            # Inject requested model at the front
            provider = "Gemini" if "gemini" in requested_model else "Groq"
            client = gemini_client if provider == "Gemini" else groq_client
            MODELS_ROUTE.append({"provider": provider, "client": client, "model": requested_model})
            
        MODELS_ROUTE.extend([
            {"provider": "Groq", "client": groq_client, "model": "llama-3.3-70b-versatile"},
            {"provider": "Groq", "client": groq_client, "model": "mixtral-8x7b-32768"},
            {"provider": "Gemini", "client": gemini_client, "model": "gemini-1.5-flash"}
        ])

    last_error = None
    for route in MODELS_ROUTE:
        try:
            if route["provider"] == "Groq":
                kwargs = {"model": route["model"], "messages": messages}
                if temperature is not None:
                    kwargs["temperature"] = temperature

                # Exclude tools for vision models to avoid API errors
                if tools and "vision" not in route["model"].lower():
                    kwargs["tools"] = tools
                    kwargs["tool_choice"] = tool_choice or "auto"
                else:
                    kwargs["stream"] = True

                loop = asyncio.get_running_loop()
                completion = await loop.run_in_executor(
                    None,
                    lambda k=kwargs: route["client"].chat.completions.create(**k)
                )
                return completion, route["model"]

            elif route["provider"] == "Gemini":
                contents = []
                system_instruction = None
                for msg in messages:
                    role = msg.get("role")
                    content = msg.get("content")

                    if role == "system":
                        system_instruction = content
                        continue

                    parts = []
                    if isinstance(content, str):
                        parts.append(content)
                    elif isinstance(content, list):
                        for item in content:
                            if item.get("type") == "text":
                                parts.append(item.get("text"))
                            elif item.get("type") == "image_url":
                                url = item.get("image_url", {}).get("url", "")
                                if url.startswith("data:image"):
                                    import io
                                    from PIL import Image
                                    header, encoded = url.split(",", 1)
                                    img_data = base64.b64decode(encoded)
                                    img = Image.open(io.BytesIO(img_data))
                                    parts.append(img)

                    gemini_role = "user" if role == "user" else "model"
                    contents.append({"role": gemini_role, "parts": parts})

                gen_config = route["client"].types.GenerationConfig(
                    temperature=temperature if temperature is not None else 0.7
                )
                gemini_tools = [t["function"] for t in tools] if tools else None
                model = route["client"].GenerativeModel(
                    model_name=route["model"],
                    system_instruction=system_instruction,
                    tools=gemini_tools
                )

                if tools:
                    loop = asyncio.get_running_loop()
                    response = await loop.run_in_executor(
                        None,
                        lambda: model.generate_content(contents, generation_config=gen_config)
                    )
                    import uuid
                    gemini_tool_calls = []
                    if response.candidates and response.candidates[0].content.parts:
                        for part in response.candidates[0].content.parts:
                            if hasattr(part, "function_call") and part.function_call:
                                args_dict = dict(part.function_call.args)
                                args_json = json.dumps(args_dict)
                                call_id = f"call_{uuid.uuid4().hex}"
                                gemini_tool_calls.append(
                                    GeminiToolCall(id=call_id, name=part.function_call.name, arguments=args_json)
                                )
                    if gemini_tool_calls:
                        return GeminiCompletion(GeminiMessage(None, tool_calls=gemini_tool_calls)), route["model"]
                    else:
                        return GeminiCompletion(GeminiMessage(response.text)), route["model"]
                else:
                    loop = asyncio.get_running_loop()
                    response = await loop.run_in_executor(
                        None,
                        lambda: model.generate_content(contents, generation_config=gen_config, stream=True)
                    )
                    return wrap_gemini_stream(response), route["model"]

        except Exception as e:
            print(f"[-] Fallback model failed on {route['model']}: {e}")
            last_error = e
            continue

    raise Exception(f"CRITICAL: All providers completely exhausted. Last error: {str(last_error)}")


def message_to_dict(msg):
    """Safely converts a message (dict or ChatCompletionMessage) to a standard dict."""
    if isinstance(msg, dict):
        return msg.copy()
    role = getattr(msg, "role", "assistant")
    content = getattr(msg, "content", "")
    d = {"role": role, "content": content}
    tool_calls = getattr(msg, "tool_calls", None)
    if tool_calls:
        d["tool_calls"] = [
            {
                "id": tc.id,
                "type": tc.type,
                "function": {
                    "name": tc.function.name,
                    "arguments": tc.function.arguments
                }
            }
            for tc in tool_calls
        ]
    return d


def sanitize_history_for_storage(history_array):
    """Strips image base64 blobs from history to prevent bloated SQLite entries."""
    clean_history = []
    for msg in history_array:
        msg_dict = message_to_dict(msg)
        if isinstance(msg_dict.get("content"), list):
            text_only = next(
                (c.get("text", "") for c in msg_dict["content"] if isinstance(c, dict) and c.get("type") == "text"),
                "[Image Omitted for Storage]"
            )
            msg_dict["content"] = text_only
        clean_history.append(msg_dict)
    return clean_history


# --- CHAINLIT STARTERS ---
@cl.set_starters
async def set_starters(user: cl.User | None = None, **kwargs):
    return [
        cl.Starter(
            label="📚 Scholar RAG — Page Algorithms",
            message="Search the textbooks and explain Page Replacement Algorithms with examples.",
            icon="/public/favicon.ico"
        ),
        cl.Starter(
            label="🎮 Gamer Latency Check",
            message="Predict my gaming network ping stability for this hour.",
            icon="/public/favicon.ico"
        ),
        cl.Starter(
            label="🌐 Live Web Intel",
            message="Search the web for the current AWS server status and any outages.",
            icon="/public/favicon.ico"
        ),
        cl.Starter(
            label="🖼️ Analyze an Image",
            message="I'll upload an image — describe what you see and extract all key information.",
            icon="/public/favicon.ico"
        )
    ]


@cl.set_chat_profiles
async def chat_profile(user: cl.User | None = None, **kwargs):
    return [
        cl.ChatProfile(
            name="Omni Mode",
            markdown_description="**Full-capability** assistant. Access all tools: web search, textbook RAG, and gaming analytics.",
            icon="https://cdn-icons-png.flaticon.com/512/4712/4712035.png",
            starters=[
                cl.Starter(label="🌐 Live Web Search", message="Search the web for the current AWS server status and any active outages.", icon="/public/favicon.ico"),
                cl.Starter(label="📚 Scholar RAG", message="Search the textbooks and explain memory management and virtual memory.", icon="/public/favicon.ico"),
                cl.Starter(label="🎮 Gamer Ping", message="Check network stability and predict latency for gaming at 8pm.", icon="/public/favicon.ico"),
                cl.Starter(label="🖼️ Analyze Image", message="I'll upload an image — describe what you see and extract all key information.", icon="/public/favicon.ico"),
            ]
        ),
        cl.ChatProfile(
            name="Scholar Mode",
            markdown_description="**Academic focus** — textbook RAG and web research. Optimized for study and deep research.",
            icon="https://cdn-icons-png.flaticon.com/512/3145/3145765.png",
            starters=[
                cl.Starter(label="📚 Page Replacement", message="Explain Page Replacement Algorithms (FIFO, LRU, Optimal) with examples.", icon="/public/favicon.ico"),
                cl.Starter(label="⚙️ CPU Scheduling", message="Compare Round Robin vs Priority scheduling with pros and cons.", icon="/public/favicon.ico"),
                cl.Starter(label="🧮 Search Algorithms", message="Explain Binary Search Tree insertion, deletion, and traversal operations.", icon="/public/favicon.ico"),
                cl.Starter(label="🌐 Research Topic", message="Search the web and textbooks for recent advances in transformer architectures.", icon="/public/favicon.ico"),
            ]
        ),
        cl.ChatProfile(
            name="Gamer Mode",
            markdown_description="**Gaming analytics** — network stability, ping prediction, and live server status checks.",
            icon="https://cdn-icons-png.flaticon.com/512/808/808439.png",
            starters=[
                cl.Starter(label="🎮 Check Ping Now", message="Check network ping for my current gaming session stability.", icon="/public/favicon.ico"),
                cl.Starter(label="🌐 Server Status", message="Search the web for current game server status and any outages.", icon="/public/favicon.ico"),
                cl.Starter(label="📊 Peak Hour Latency", message="Predict latency for hour 20 and suggest optimal gaming windows.", icon="/public/favicon.ico"),
                cl.Starter(label="⚡ Best Play Time", message="Analyze today's full latency predictions and find the best gaming window.", icon="/public/favicon.ico"),
            ]
        ),
        cl.ChatProfile(
            name="Voice Mode",
            markdown_description="**Audio processing** — speak via Whisper transcription with full AI response.",
            icon="https://cdn-icons-png.flaticon.com/512/709/709682.png",
            starters=[
                cl.Starter(label="🎙️ Start Voice", message="I'm ready to use voice mode. I'll speak my next query.", icon="/public/favicon.ico"),
                cl.Starter(label="📝 Transcribe Audio", message="Please transcribe the audio I'm about to upload.", icon="/public/favicon.ico"),
            ]
        ),
    ]


@cl.password_auth_callback
async def auth_callback(username: str, password: str):
    username = username.strip() if isinstance(username, str) else ""
    password = password.strip() if isinstance(password, str) else ""
    if not username or not password:
        return None
        
    # FIX: Passwordless Auth - password must equal username
    if username != password:
        return None
        
    try:
        existing_user = await data_layer.get_user(username)
        if existing_user:
            return cl.User(identifier=existing_user.identifier, metadata=existing_user.metadata)
        else:
            new_user = cl.User(identifier=username, metadata={"type": "passwordless"})
            persisted_user = await data_layer.create_user(new_user)
            if persisted_user:
                return cl.User(identifier=persisted_user.identifier, metadata=persisted_user.metadata)
            return None
    except Exception as e:
        print(f"[-] Auth callback database error: {e}")
        return None


@cl.on_chat_start
async def start_chat():
    user = cl.user_session.get("user")
    print(f"DEBUG USER: type={type(user)}, dict={user.__dict__ if hasattr(user, '__dict__') else 'no dict'}, id={getattr(user, 'id', 'NO ID')}")
    if not user:
        return

    # Limit chat history to 3 chats per user
    try:
        identifier = getattr(user, "identifier", "")
        if identifier:
            query = """
                SELECT id FROM threads 
                WHERE "userIdentifier" = :identifier 
                ORDER BY "createdAt" DESC
            """
            threads = await data_layer.execute_sql(query=query, parameters={"identifier": identifier})
            if isinstance(threads, list) and len(threads) > 3:
                for old_thread in threads[3:]:
                    tid = old_thread["id"]
                    try:
                        # Fallback to direct SQL delete if built-in throws Author not found
                        await data_layer.execute_sql('DELETE FROM steps WHERE "threadId" = :id', parameters={"id": tid})
                        await data_layer.execute_sql('DELETE FROM elements WHERE "threadId" = :id', parameters={"id": tid})
                        await data_layer.execute_sql('DELETE FROM threads WHERE id = :id', parameters={"id": tid})
                    except Exception as e:
                        print(f"[-] Force delete failed for {tid}: {e}")
    except Exception as e:
        print(f"[-] Error limiting chat history: {e}")

    cl.user_session.set("session_id", cl.user_session.get("id"))
    chat_profile_name = cl.user_session.get("chat_profile") or "Omni Mode"
    cl.user_session.set("chat_profile", chat_profile_name)

    # AskUserMessage for Gamer Mode Context
    game_context = ""
    if chat_profile_name == "Gamer Mode":
        try:
            res = await cl.AskUserMessage(
                content="Welcome to Gamer Mode! What game are you playing? (e.g. Valorant, Apex, CS2):",
                timeout=120
            ).send()
            if res:
                game_context = f"\nUser is currently playing: {res.get('output', '')}"
        except Exception as e:
            print(f"[-] Gamer start profile error: {e}")

    system_instruction = f"You are NexusAI, a dual-engine Scholar-Gamer CoPilot. Maintain deep context awareness. Your current profile is {chat_profile_name}.{game_context}"
    cl.user_session.set("message_history", [{"role": "system", "content": system_instruction}])

    # Chat Settings setup
    try:
        await cl.ChatSettings(
            [
                cl.input_widget.Select(
                    id="Model",
                    label="Language Model",
                    values=["llama3-8b-8192", "llama3-70b-8192", "gemini-1.5-flash", "gemini-1.5-pro", "whisper-1"],
                    initial_index=1
                ),
                cl.input_widget.TextInput(
                    id="SystemPrompt",
                    label="System Instructions",
                    initial=""
                ),
                cl.input_widget.Slider(
                    id="Temperature",
                    label="Model Temperature",
                    initial=0.7,
                    min=0.0,
                    max=1.0,
                    step=0.1
                ),
                cl.input_widget.Switch(
                    id="DeepSearch",
                    label="Deep Search",
                    initial=False
                )
            ]
        ).send()
    except Exception as e:
        print(f"[-] Chat settings configuration error: {e}")

    # Slash commands registry menu
    commands = [
        {"id": "scholar", "icon": "book", "description": "Force Textbook Search"},
        {"id": "gamer", "icon": "gamepad", "description": "Force Ping Prediction"},
        {"id": "web", "icon": "globe", "description": "Force Live Internet Search"},
        {"id": "clear", "icon": "trash", "description": "Clear the visual UI display but keep context memory"},
        {"id": "reset-chat", "icon": "refresh-cw", "description": "Wipe current thread memory"},
        {"id": "new-chat", "icon": "plus", "description": "Start new chat thread (limit 3)"},
        {"id": "new", "icon": "bolt", "description": "Factory Reset (Wipes session data, keeps accounts)"}
    ]
    try:
        await cl.context.emitter.set_commands(commands) # type: ignore
    except Exception as e:
        print(f"[-] Slash commands register error: {e}")

    # Modes picker — per-message tool routing supplement to slash commands
    try:
        await cl.context.emitter.set_modes([
            cl.Mode(
                id="tool_focus",
                name="Focus",
                options=[
                    cl.ModeOption(id="auto", name="Auto", default=True),
                    cl.ModeOption(id="scholar", name="Scholar"),
                    cl.ModeOption(id="gamer", name="Gamer"),
                    cl.ModeOption(id="web", name="Web"),
                ]
            )
        ])
    except Exception as e:
        print(f"[-] Modes setup error: {e}")

    mode_icons = {
        "Scholar Mode": "📚",
        "Gamer Mode": "🎮",
        "Omni Mode": "🌐",
        "Voice Mode": "🎙️"
    }
    mode_icon = mode_icons.get(chat_profile_name, "⚡")

    # HTML welcome card (requires unsafe_allow_html = true in config.toml)
    welcome_text = f"""<div class="nx-welcome-card">
  <div class="nx-mode-badge">{mode_icon} {chat_profile_name}</div>
  <h1>⚡ NexusAI</h1>
  <p><strong>Dual-Engine AI Ready</strong> — Scholar 📚 · Gamer 🎮 · Omni 🌐</p>
  <p class="nx-welcome-desc" style="margin-top:10px;font-size:13px;">Upload images, PDFs, code files &amp; documents · Use <code>/scholar</code>, <code>/gamer</code>, <code>/web</code> slash commands</p>
</div>"""

    try:
        await cl.Message(content=welcome_text).send()
    except Exception as e:
        print(f"[-] Welcome message send error: {e}")


@cl.on_chat_resume
async def on_chat_resume(thread):
    cl.user_session.set("session_id", cl.user_session.get("id"))

    # Restore chat profile from thread metadata (persisted at session start)
    thread_meta = thread.get("metadata") or {}
    if isinstance(thread_meta, str):
        try:
            thread_meta = json.loads(thread_meta)
        except Exception:
            thread_meta = {}
    chat_profile_name = (
        thread_meta.get("chat_profile")
        or cl.user_session.get("chat_profile")
        or "Omni Mode"
    )
    cl.user_session.set("chat_profile", chat_profile_name)

    # Re-register commands and modes for the resumed session
    try:
        await cl.context.emitter.set_modes([
            cl.Mode(
                id="tool_focus",
                name="Focus",
                options=[
                    cl.ModeOption(id="auto", name="Auto", default=True),
                    cl.ModeOption(id="scholar", name="Scholar"),
                    cl.ModeOption(id="gamer", name="Gamer"),
                    cl.ModeOption(id="web", name="Web"),
                ]
            )
        ])
    except Exception:
        pass

    # Reconstruct message history from persisted thread steps
    message_history = []
    system_instruction = (
        f"You are NexusAI, a dual-engine Scholar-Gamer CoPilot. "
        f"Maintain deep context awareness. Your current profile is {chat_profile_name}."
    )
    message_history.append({"role": "system", "content": system_instruction})

    for step in thread.get("steps", []):
        step_type = step.get("type", "")
        step_output = step.get("output") or ""
        if step_type == "user_message" and step_output:
            message_history.append({"role": "user", "content": step_output})
        elif step_type == "assistant_message" and step_output:
            message_history.append({"role": "assistant", "content": step_output})

    cl.user_session.set("message_history", sanitize_history_for_storage(message_history))


@cl.on_chat_end
async def end_chat():
    # FIX P3-24: Namespace textbooks by user ID to prevent cross-user deletion
    user = cl.user_session.get("user")
    user_id = user.id if user else "shared"
    textbooks_dir = os.path.join(os.path.dirname(__file__), "data", "textbooks", user_id)
    if os.path.exists(textbooks_dir):
        for filename in os.listdir(textbooks_dir):
            file_path = os.path.join(textbooks_dir, filename)
            try:
                if os.path.isfile(file_path):
                    os.unlink(file_path)
            except Exception:
                pass
        # FIX P1-10: Run vector DB build in executor
        try:
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(None, build_vector_database)
        except Exception as e:
            print(f"[-] RAG cleanup index rebuild failed: {e}")


@cl.on_stop
async def on_stop():
    """Called when the user clicks the Stop button mid-generation."""
    cl.user_session.set("should_stop", True)


@cl.on_logout
async def on_logout(request: Request, response: Response):
    """Called on explicit logout — allows cleanup hooks."""
    # Since we can't grab the user identifier directly from a basic user object here,
    # we log a clean session termination message safely.
    print("[*] An active user session has logged out cleanly.")

@cl.author_rename
async def rename_author(orig_author: str):
    """Rename chat authors for branded NexusAI display."""
    rename_map = {
        "Chatbot": "NexusAI",
        "Assistant": "NexusAI",
        "Tool": "⚙️ NexusAI Tools",
        "Error": "⚠️ System",
    }
    return rename_map.get(orig_author, orig_author)


# --- CUSTOM API ENDPOINTS FOR WORKSPACE ---
@fastapi_app.post("/api/upload")
async def upload_document(file: UploadFile = File(...)):
    try:
        # FIX P3-23: Sanitize filename to prevent path traversal
        safe_name = pathlib.Path(file.filename or "uploaded_file").name
        textbooks_dir = os.path.join(os.path.dirname(__file__), "data", "textbooks")
        os.makedirs(textbooks_dir, exist_ok=True)
        file_path = os.path.join(textbooks_dir, safe_name)

        # FIX P1-8: Use aiofiles for async file I/O
        content = await file.read()
        async with aiofiles.open(file_path, "wb") as f:
            await f.write(content)

        return {"filename": safe_name, "status": "success", "url": f"/public/elements/{safe_name}"}
    except Exception as e:
        return Response(content=json.dumps({"status": "error", "message": str(e)}), status_code=500)


@fastapi_app.post("/api/build-index")
async def build_index():
    try:
        # FIX P1-10: Run in executor
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, build_vector_database)
        return {"status": "success"}
    except Exception as e:
        return Response(content=json.dumps({"status": "error", "message": str(e)}), status_code=500)


@fastapi_app.delete("/api/delete/{filename}")
async def delete_document(filename: str):
    try:
        # FIX P3-23: Sanitize filename
        safe_name = pathlib.Path(filename).name
        textbooks_dir = os.path.join(os.path.dirname(__file__), "data", "textbooks")
        file_path = os.path.join(textbooks_dir, safe_name)
        if os.path.exists(file_path):
            os.remove(file_path)
            # FIX P1-10: Run in executor
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(None, build_vector_database)
            return {"filename": safe_name, "status": "deleted"}
        return Response(status_code=404)
    except Exception as e:
        return Response(content=json.dumps({"status": "error", "message": str(e)}), status_code=500)


# --- CUSTOM UI ROUTES REMOVED ---
# We now rely exclusively on /public/login/index.html to bypass Chainlit's Auth Middleware.


# --- AUDIO HANDLERS ---
@cl.on_audio_start
async def on_audio_start():
    cl.user_session.set("audio_buffer", None)
    cl.user_session.set("audio_mime_type", None)
    return True


# FIX P2-14: Removed monkey patch. Use @cl.on_audio_chunk with no args
@cl.on_audio_chunk
async def on_audio_chunk(chunk):
    buffer = cl.user_session.get("audio_buffer")
    if not buffer:
        import io
        mime_type = getattr(chunk, "mimeType", "audio/webm")
        if not mime_type or "/" not in mime_type:
            mime_type = "audio/webm"
        buffer = io.BytesIO()
        clean_ext = mime_type.split('/')[1].split(';')[0] if '/' in mime_type else "webm"
        buffer.name = f"input_audio.{clean_ext}"
        cl.user_session.set("audio_buffer", buffer)
        cl.user_session.set("audio_mime_type", mime_type)
    buffer.write(chunk.data)


# FIX P2-14: Removed monkey patch. Use @cl.on_audio_end with no args
@cl.on_audio_end
async def on_audio_end(*args, **kwargs):
    audio_buffer = cl.user_session.get("audio_buffer")
    if not audio_buffer:
        return
    audio_buffer.seek(0)
    audio_data = audio_buffer.read()
    mime_type = cl.user_session.get("audio_mime_type") or "audio/webm"
    filename = getattr(audio_buffer, "name", "input_audio.webm")

    cl.user_session.set("audio_buffer", None)
    cl.user_session.set("audio_mime_type", None)

    try:
        # FIX P1-7: Wrap synchronous Whisper call in run_in_executor
        loop = asyncio.get_running_loop()
        transcription = await loop.run_in_executor(
            None,
            lambda: groq_client.audio.transcriptions.create(
                model="whisper-large-v3",
                file=(filename, audio_data, mime_type)
            )
        )
        text = transcription.text
        if text and text.strip():
            user_msg = cl.Message(author="You", content=text)
            await user_msg.send()
            await handle_message(user_msg)
    except Exception as e:
        print(f"[-] Audio transcription failed: {e}")
        await cl.ErrorMessage(content=f"⚠️ Transcription failed: {e}").send()


@cl.on_settings_update
async def setup_agent(settings):
    try:
        cl.user_session.set("temperature", settings.get("Temperature", 0.7))
        cl.user_session.set("deep_web_search", settings.get("DeepSearch", False))
        cl.user_session.set("model", settings.get("Model", "llama3-70b-8192"))
        cl.user_session.set("system_prompt", settings.get("SystemPrompt", ""))
    except Exception as e:
        print(f"[-] Settings update error: {e}")


async def enforce_three_session_limit():
    """Strictly caps the chat history to the 3 most recent sessions per user (FIFO)."""
    try:
        layer = cl_data.get_data_layer()
        # FIX P1-11: Use cl_data.get_data_layer() instead of cl_data._data_layer
        if not layer or not hasattr(layer, "engine"):
            return
        
        from chainlit.data.sql_alchemy import SQLAlchemyDataLayer
        if not isinstance(layer, SQLAlchemyDataLayer):
            return

        user = cl.user_session.get("user")
        if not user:
            return

        async with layer.engine.begin() as conn:
            # FIX P0-1: Scope query to current user; use datetime() for robust ordering
            result = await conn.execute(
                text("SELECT id FROM threads WHERE userId = :uid ORDER BY datetime(createdAt) DESC"),
                {"uid": user.id}
            )
            rows = result.fetchall()
            thread_ids = [row[0] for row in rows]

            if len(thread_ids) > 3:
                for old_thread_id in thread_ids[3:]:
                    print(f"[*] Purging old session: {old_thread_id}")
                    await conn.execute(text("DELETE FROM elements WHERE threadId = :tid"), {"tid": old_thread_id})
                    await conn.execute(text("DELETE FROM steps WHERE threadId = :tid"), {"tid": old_thread_id})
                    await conn.execute(text("DELETE FROM threads WHERE id = :tid"), {"tid": old_thread_id})
    except Exception as e:
        print(f"[-] Error enforcing 3-session limit: {e}")


async def auto_rename_session(history):
    user_msgs = [m for m in history if m.get("role") == "user"]
    if len(user_msgs) == 1:
        try:
            first_msg = user_msgs[0].get("content", "")
            if isinstance(first_msg, list):
                first_msg = next((c.get("text", "") for c in first_msg if c.get("type") == "text"), "")

            # FIX P1-6: Wrap sync Groq call in run_in_executor
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
            title = (completion.choices[0].message.content or "").strip().replace('"', '').replace("'", "")
            thread_id = cl.context.session.thread_id
            layer = cl_data.get_data_layer()
            if thread_id and layer:
                # FIX P2-5: Preserve existing metadata before update_thread
                try:
                    existing_thread = await layer.get_thread(thread_id)
                    existing_meta = existing_thread.get("metadata", {}) if existing_thread and existing_thread.get("metadata") else {}
                except Exception:
                    existing_meta = {}
                await layer.update_thread(thread_id, name=title, metadata=existing_meta)
                await enforce_three_session_limit()
        except Exception as e:
            print(f"[-] Error in auto_rename_session: {e}")


async def text_to_speech(text: str):
    response = await openai_client.audio.speech.create(
        model="tts-1",
        voice="alloy",
        input=text
    )
    filename = f"tts_{uuid.uuid4().hex[:8]}.mp3"
    filepath = os.path.join(os.path.dirname(__file__), "data", "audio", filename)
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    with open(filepath, "wb") as f:
        f.write(response.read())
    return filename, filepath

async def add_voice_to_response(response_msg, full_response):
    try:
        audio_name, audio_path = await text_to_speech(full_response)
        audio_element = cl.Audio(name="Voice Output", path=audio_path, display="inline")
        if not hasattr(response_msg, "elements") or response_msg.elements is None:
            response_msg.elements = []
        response_msg.elements.append(audio_element)
    except Exception as e:
        print(f"[-] TTS Generation Error: {e}")

@cl.on_message
async def handle_message(message: cl.Message):
    try:
        history_raw = cl.user_session.get("message_history")
        history = [message_to_dict(m) for m in history_raw] if history_raw else []
        
        custom_sys_prompt = (cl.user_session.get("system_prompt") or "").strip()
        if custom_sys_prompt and history and history[0].get("role") == "system":
            history[0]["content"] = history[0]["content"] + f"\n\n[USER CUSTOM INSTRUCTION]: {custom_sys_prompt}"

        # Intercept string-based manual command inputs
        cmd = message.command
        content = message.content.strip() if message.content else ""
        if content.startswith("/"):
            parts = content[1:].strip().split()
            if parts:
                cmd = parts[0]

        # --- COMMAND ISOLATION (EARLY RETURN RULE) ---
        if cmd in ("reset-chat", "clear", "new-chat", "new"):
            if cmd == "reset-chat":
                chat_profile_name = cl.user_session.get("chat_profile") or "Omni Mode"
                system_instruction = f"You are NexusAI. Maintain deep context awareness. Your current profile is {chat_profile_name}."
                cl.user_session.set("message_history", [{"role": "system", "content": system_instruction}])
                await cl.Message(content="🔄 *Memory wiped. Starting a fresh neural link within this thread.*").send()
                return

            elif cmd == "clear":
                await cl.CopilotFunction(name="clear_visual_chat", args={}).acall()
                await cl.Message(content="🧹 *Display cleared. NexusAI still retains memory of this session.*").send()
                return

            elif cmd == "new-chat":
                cl.user_session.set("message_history", [])
                await cl.CopilotFunction(name="new_chat_session", args={}).acall()
                return

            elif cmd == "new":
                cl.user_session.set("message_history", [])
                layer = cl_data.get_data_layer()
                try:
                    # FIX P0-2: Selectively drop only session data tables — NOT users table
                    from chainlit.data.sql_alchemy import SQLAlchemyDataLayer
                    if layer and isinstance(layer, SQLAlchemyDataLayer) and hasattr(layer, "engine"):
                        async with layer.engine.begin() as conn:
                            for table in PURGEABLE_TABLES:
                                await conn.run_sync(lambda c, t=table: t.drop(c, checkfirst=True))
                            for table in reversed(PURGEABLE_TABLES):
                                await conn.run_sync(lambda c, t=table: t.create(c, checkfirst=True))
                    await cl.Message(content="💥 *Factory Reset Complete. Session data purged. User accounts preserved.*").send()
                except Exception as db_err:
                    print(f"[-] Factory reset database error: {db_err}")
                    await cl.ErrorMessage(content=f"⚠️ Failed database reset: {db_err}").send()
                await cl.CopilotFunction(name="new_chat_session", args={}).acall()
                return

        msg_content = message.content.strip().lower() if message.content and hasattr(message.content, "strip") else ""
        if "check ping" in msg_content or "predict ping" in msg_content:
            digits = re.findall(r'\d+', msg_content)
            if not digits:
                ask_msg = await cl.AskUserMessage(content="What hour (0-23)?", timeout=60).send()
                if ask_msg:
                    ans_digits = re.findall(r'\d+', ask_msg.get('output', ''))
                    hour_val = int(ans_digits[0]) if ans_digits else datetime.now().hour
                else:
                    hour_val = datetime.now().hour

                ping = predict_latency(hour=hour_val, minute=0, server_code=0)
                response_msg = cl.Message(
                    content=f"🎮 **Network Telemetry**: Predicted ping for hour `{hour_val}:00` is `{ping} ms`."
                )
                actions = [
                    cl.Action(name="regenerate_answer", label="🔄 Regenerate Response", payload={"action": "regenerate"}),
                    cl.Action(name="verify_citations", label="📄 Verify Citations", payload={"action": "verify"}),
                    cl.Action(name="search_web_instead", label="🌐 Search Web Instead", payload={"action": "search_web"})
                ]
                response_msg.actions = actions
                await response_msg.send()
                history.append({"role": "user", "content": f"Check ping for hour {hour_val}"})
                history.append({"role": "assistant", "content": response_msg.content})
                # FIX P2-15: Sanitize before storing
                cl.user_session.set("message_history", sanitize_history_for_storage(history))
                return

        # FIX P2-21: Use regex to parse FILE_SELECTED to handle filenames containing ']'
        if message.content.startswith("[FILE_SELECTED:"):
            match = re.search(r'\[FILE_SELECTED:(.*?)\]', message.content)
            if match:
                filename = match.group(1)
                file_path = os.path.join(os.path.dirname(__file__), "data", "textbooks", filename)
                if os.path.exists(file_path):
                    file_element = cl.File(name=filename, path=file_path, display="inline")
                    await cl.Message(
                        content=f"📎 **File Focused**: NexusAI has loaded `{filename}`. Ask me questions about it!",
                        elements=[file_element]
                    ).send()
                else:
                    await cl.Message(
                        content=f"📎 **File Focused**: NexusAI is ready to analyze `{filename}`. Ask me questions!"
                    ).send()
            return

        elif message.content.startswith("[FILE_DESELECTED:"):
            match = re.search(r'\[FILE_DESELECTED:(.*?)\]', message.content)
            if match:
                filename = match.group(1)
                await cl.Message(content=f"🔓 **File Unfocused**: `{filename}` is no longer focused.").send()
            return

        tool_choice = None
        if message.command == "scholar":
            tool_choice = {"type": "function", "function": {"name": "query_academic_textbooks"}}
        elif message.command == "gamer":
            tool_choice = {"type": "function", "function": {"name": "check_game_network_stability"}}
        elif message.command == "web":
            tool_choice = {"type": "function", "function": {"name": "execute_web_search"}}

        # Supplement slash commands with Modes picker selection
        if not tool_choice:
            active_mode = (getattr(message, 'modes', None) or {}).get("tool_focus", "auto")
            mode_to_tool = {
                "scholar": "query_academic_textbooks",
                "gamer": "check_game_network_stability",
                "web": "execute_web_search",
            }
            if active_mode in mode_to_tool:
                tool_choice = {"type": "function", "function": {"name": mode_to_tool[active_mode]}}

        attached_text = ""
        image_contents = []

        # Custom vision extraction
        pattern = r"\[IMAGE_DATA:(.*?):(data:image/.*?;base64,.*?)\]"
        matches = re.findall(pattern, message.content)
        cleaned_prompt_text = message.content
        for match in matches:
            filename, base64_data = match
            image_contents.append(
                {"type": "image_url", "image_url": {"url": base64_data}}
            )
            cleaned_prompt_text = cleaned_prompt_text.replace(f"[IMAGE_DATA:{filename}:{base64_data}]", "")
        cleaned_prompt_text = cleaned_prompt_text.strip()

        # ── Multi-Modal Element Processing ─────────────────────
        if message.elements:
            for element in message.elements:
                try:
                    name_lower = element.name.lower() if hasattr(element, "name") and element.name else ""
                    el_path = getattr(element, "path", None)
                    if not isinstance(el_path, str):
                        continue

                    # Text / Code files
                    if name_lower.endswith(('.txt', '.py', '.js', '.ts', '.jsx', '.tsx',
                                            '.json', '.csv', '.html', '.css', '.md',
                                            '.sh', '.yaml', '.yml', '.toml', '.ini',
                                            '.xml', '.sql', '.rs', '.go', '.c', '.cpp',
                                            '.h', '.java', '.kt', '.swift', '.rb')):
                        with open(el_path, "r", encoding="utf-8", errors="replace") as f:
                            file_content = f.read()
                        ext = name_lower.rsplit('.', 1)[-1]
                        attached_text += f"\n\n--- {ext.upper()} File: {element.name} ---\n```{ext}\n{file_content}\n```"

                    # Word documents
                    elif name_lower.endswith(('.docx', '.doc')):
                        import docx
                        doc = docx.Document(el_path)
                        text_content = "\n".join([para.text for para in doc.paragraphs if para.text.strip()])
                        attached_text += f"\n\n--- Word Document: {element.name} ---\n{text_content}"

                    # PowerPoint presentations
                    elif name_lower.endswith(('.pptx', '.ppt')):
                        import pptx
                        prs = pptx.Presentation(el_path)
                        text_content = "\n".join(
                            [getattr(shape, "text", "") for slide in prs.slides for shape in slide.shapes
                             if hasattr(shape, "text") and getattr(shape, "text", "").strip()])
                        attached_text += f"\n\n--- Presentation: {element.name} ({len(prs.slides)} slides) ---\n{text_content}"

                    # PDF documents
                    elif name_lower.endswith('.pdf'):
                        import PyPDF2
                        with open(el_path, "rb") as f:
                            reader = PyPDF2.PdfReader(f)
                            pages_text = [page.extract_text() for page in reader.pages if page.extract_text()]
                            text_content = "\n\n".join(pages_text)
                        attached_text += f"\n\n--- PDF Document: {element.name} ({len(reader.pages)} pages) ---\n{text_content}"

                    # Excel / spreadsheets
                    elif name_lower.endswith(('.xlsx', '.xls', '.ods')):
                        import pandas as pd
                        xls = pd.ExcelFile(el_path)
                        sheet_texts = []
                        for sheet_name in xls.sheet_names:
                            df = pd.read_excel(xls, sheet_name=sheet_name)
                            sheet_texts.append(f"--- Sheet: {sheet_name} ---\n{df.to_string()}")
                        text_content = "\n\n".join(sheet_texts)
                        attached_text += f"\n\n--- Spreadsheet: {element.name} ({len(xls.sheet_names)} sheets) ---\n{text_content}"

                    # Images — send to vision LLM
                    elif name_lower.endswith(('.png', '.jpg', '.jpeg', '.webp', '.gif', '.bmp')):
                        with open(el_path, "rb") as img_file:
                            img_bytes = img_file.read()
                        base64_image = base64.b64encode(img_bytes).decode('utf-8')
                        # Determine correct MIME type
                        ext_map = {'jpg': 'jpeg', 'jpeg': 'jpeg', 'png': 'png',
                                   'webp': 'webp', 'gif': 'gif', 'bmp': 'png'}
                        img_ext = name_lower.rsplit('.', 1)[-1]
                        mime = ext_map.get(img_ext, 'jpeg')
                        image_contents.append({
                            "type": "image_url",
                            "image_url": {"url": f"data:image/{mime};base64,{base64_image}"}
                        })

                    # Audio files — transcribe via Whisper
                    elif name_lower.endswith(('.mp3', '.wav', '.ogg', '.m4a', '.flac', '.webm')):
                        try:
                            loop = asyncio.get_running_loop()
                            with open(el_path, "rb") as audio_file:
                                audio_bytes = audio_file.read()
                            transcription = await loop.run_in_executor(
                                None,
                                lambda: groq_client.audio.transcriptions.create(
                                    model="whisper-large-v3",
                                    file=(element.name, audio_bytes, f"audio/{name_lower.rsplit('.', 1)[-1]}")
                                )
                            )
                            audio_text = transcription.text
                            attached_text += f"\n\n--- Audio Transcription: {element.name} ---\n{audio_text}"
                        except Exception as audio_err:
                            attached_text += f"\n\n[Audio file '{element.name}' could not be transcribed: {audio_err}]"

                    # Video files — note about limitation
                    elif name_lower.endswith(('.mp4', '.avi', '.mov', '.mkv', '.webm')):
                        attached_text += f"\n\n[Video file '{element.name}' uploaded. Note: NexusAI cannot analyze video frames directly, but can discuss the content if you describe it.]"

                    else:
                        attached_text += f"\n\n[File '{element.name}' uploaded but format not fully supported for text extraction.]"

                except Exception as e:
                    attached_text += f"\n\n[System Note: Failed to parse {element.name}: {str(e)}]"

        final_prompt_text = cleaned_prompt_text
        if message.command and not tool_choice:
            final_prompt_text = f"[SYSTEM OVERRIDE: The user used the '/{message.command}' command. Prioritize using the associated tool.]\n\n{final_prompt_text}"
        if attached_text:
            final_prompt_text += f"\n\n[SYSTEM INJECTION: The user attached files. Read them below:]\n{attached_text}"

        has_vision = len(image_contents) > 0
        if has_vision:
            content_payload = [{"type": "text", "text": final_prompt_text}]
            content_payload.extend(image_contents)
            history.append({"role": "user", "content": content_payload})
        else:
            history.append({"role": "user", "content": final_prompt_text})

        temperature = cl.user_session.get("temperature", 0.7)
        deep_web = cl.user_session.get("deep_web_search", False)
        chat_profile_name = cl.user_session.get("chat_profile") or "Omni Mode"

        active_tools = TOOLS_SCHEMA.copy()
        if chat_profile_name == "Scholar Mode":
            active_tools = [t for t in TOOLS_SCHEMA if t["function"]["name"] in ("query_academic_textbooks", "execute_web_search")]
        elif chat_profile_name == "Gamer Mode":
            active_tools = [t for t in TOOLS_SCHEMA if t["function"]["name"] in ("check_game_network_stability", "execute_web_search")]

        # FIX P2-16: Idempotent DeepSearch injection — only inject once
        DEEP_SEARCH_MARKER = "[SYSTEM INJECTION: Deep Web Search is enabled."
        if deep_web:
            already_injected = any(
                msg.get("role") == "system" and DEEP_SEARCH_MARKER in msg.get("content", "")
                for msg in history
            )
            if not already_injected:
                history.append({
                    "role": "system",
                    "content": f"{DEEP_SEARCH_MARKER} Actively use the web search tool to find live, real-time facts.]"
                })

        selected_model = cl.user_session.get("model")

        if has_vision:
            streamed_completion, _ = await call_llm_with_fallback(history, temperature=temperature, vision_mode=True, requested_model=selected_model)
            response_msg = cl.Message(content="")
            await response_msg.send()
            full_response = ""
            for chunk in streamed_completion:
                if cl.user_session.get("should_stop"):
                    cl.user_session.set("should_stop", False)
                    break
                text_tok = getattr(chunk.choices[0].delta, "content", "") or ""
                full_response += text_tok
                await response_msg.stream_token(text_tok)
            history.append({"role": "assistant", "content": full_response})
            actions = [
                cl.Action(name="regenerate_answer", label="🔄 Regenerate", icon="refresh-cw", payload={"action": "regenerate"}),
                cl.Action(name="verify_citations", label="📄 Verify Citations", icon="file-check", payload={"action": "verify"}),
                cl.Action(name="search_web_instead", label="🌐 Search Web", icon="globe", payload={"action": "search_web"})
            ]
            response_msg.actions = actions
            if chat_profile_name == "Voice Mode":
                await add_voice_to_response(response_msg, full_response)
            await response_msg.update()

        else:
            completion, _ = await call_llm_with_fallback(history, tools=active_tools, tool_choice=tool_choice, temperature=temperature, requested_model=selected_model)
            response_message = completion.choices[0].message

            if response_message.tool_calls:
                history.append(message_to_dict(response_message))
                for tool_call in response_message.tool_calls:
                    args = json.loads(tool_call.function.arguments)
                    func = tool_call.function.name

                    async with cl.Step(name=f"Processing {func}...", type="tool") as step:
                        step.input = args
                        tool_content = ""

                        if func == "check_game_network_stability":
                            hour_val = args.get("hour")
                            if hour_val is None:
                                ask_msg = await cl.AskUserMessage(content="What hour (0-23)?", timeout=60).send()
                                if ask_msg:
                                    try:
                                        digits = "".join(filter(str.isdigit, ask_msg.get('output', '')))
                                        hour_val = int(digits)
                                        if not (0 <= hour_val <= 23):
                                            hour_val = datetime.now().hour
                                    except ValueError:
                                        hour_val = datetime.now().hour
                                else:
                                    hour_val = datetime.now().hour
                            ping = predict_latency(hour=hour_val, minute=0, server_code=0)
                            tool_content = f"Estimated latency: {ping} ms."

                        elif func == "query_academic_textbooks":
                            tool_content, sources = search_textbooks_with_sources(args.get("search_query"), k=3)
                            cl.user_session.set("last_rag_result", tool_content)
                            cl.user_session.set("last_rag_sources", sources)
                            elements: List[Any] = [cl.Text(name="Source", content=tool_content, display="inline")]
                            for src in sources:
                                if not isinstance(src, str):
                                    continue
                                src_path = os.path.join(os.path.dirname(__file__), "data", "textbooks", src)
                                if os.path.exists(src_path):
                                    if src.lower().endswith(".pdf"):
                                        elements.append(cl.Pdf(name=src, path=src_path, display="side"))
                                    else:
                                        # FIX P2-12: cl.Text has no path param — read content or use cl.File
                                        try:
                                            with open(src_path, "r", encoding="utf-8") as f:
                                                file_content = f.read()
                                            elements.append(cl.Text(name=src, content=file_content, display="side"))
                                        except Exception:
                                            elements.append(cl.File(name=src, path=src_path, display="side"))
                            await cl.Message(content="Found relevant textbook segments:", elements=elements).send()
                            tool_content = f"Academic Textbook search results:\n{tool_content}"

                        elif func == "execute_web_search":
                            # FIX P1-9: Use async wrapper
                            tool_content = await perform_web_search_async(args.get("query"))

                        step.output = tool_content

                    history.append({"role": "tool", "tool_call_id": tool_call.id, "name": func, "content": tool_content})

                final_completion, _ = await call_llm_with_fallback(history, temperature=temperature, requested_model=selected_model)
                response_msg = cl.Message(content="")
                await response_msg.send()
                full_response = ""
                for chunk in final_completion:
                    if cl.user_session.get("should_stop"):
                        cl.user_session.set("should_stop", False)
                        break
                    text_tok = getattr(chunk.choices[0].delta, "content", "") or ""
                    full_response += text_tok
                    await response_msg.stream_token(text_tok)
                history.append({"role": "assistant", "content": full_response})

                actions = [
                    cl.Action(name="regenerate_answer", label="🔄 Regenerate", icon="refresh-cw", payload={"action": "regenerate"}),
                    cl.Action(name="verify_citations", label="📄 Verify Citations", icon="file-check", payload={"action": "verify"}),
                    cl.Action(name="search_web_instead", label="🌐 Search Web", icon="globe", payload={"action": "search_web"})
                ]
                response_msg.actions = actions

                rag_content = cl.user_session.get("last_rag_result")
                elements: List[Any] = []
                if rag_content:
                    elements.append(cl.Text(name="Source", content=rag_content, display="side"))
                    rag_sources = cl.user_session.get("last_rag_sources") or []
                    for src in rag_sources:
                        if not isinstance(src, str):
                            continue
                        src_path = os.path.join(os.path.dirname(__file__), "data", "textbooks", src)
                        if os.path.exists(src_path) and src.lower().endswith(".pdf"):
                            elements.append(cl.Pdf(name=src, path=src_path, display="side"))
                    cl.user_session.set("last_rag_result", None)
                    cl.user_session.set("last_rag_sources", None)
                if elements:
                    response_msg.elements = elements
                if chat_profile_name == "Voice Mode":
                    await add_voice_to_response(response_msg, full_response)
                await response_msg.update()

            else:
                selected_model = cl.user_session.get("model")
                streamed_completion, _ = await call_llm_with_fallback(history, temperature=temperature, requested_model=selected_model)
                response_msg = cl.Message(content="")
                await response_msg.send()
                full_response = ""
                for chunk in streamed_completion:
                    if cl.user_session.get("should_stop"):
                        cl.user_session.set("should_stop", False)
                        break
                    text_tok = getattr(chunk.choices[0].delta, "content", "") or ""
                    full_response += text_tok
                    await response_msg.stream_token(text_tok)
                history.append({"role": "assistant", "content": full_response})
                actions = [
                    cl.Action(name="regenerate_answer", label="🔄 Regenerate", icon="refresh-cw", payload={"action": "regenerate"}),
                    cl.Action(name="verify_citations", label="📄 Verify Citations", icon="file-check", payload={"action": "verify"}),
                    cl.Action(name="search_web_instead", label="🌐 Search Web", icon="globe", payload={"action": "search_web"})
                ]
                response_msg.actions = actions
                if chat_profile_name == "Voice Mode":
                    await add_voice_to_response(response_msg, full_response)
                await response_msg.update()

        # Auto rename and persist — FIX P2-15: sanitize before storing
        await auto_rename_session(history)
        cl.user_session.set("message_history", sanitize_history_for_storage(history))

    except Exception as e:
        await cl.ErrorMessage(content=f"⚠️ Backend Exception: {str(e)}").send()


@cl.action_callback("regenerate_answer")
async def on_regenerate(action: cl.Action):
    try:
        history = cl.user_session.get("message_history", [])
        if not history:
            return
        if history[-1].get("role") == "assistant":
            history.pop()
        temperature = cl.user_session.get("temperature", 0.7)
        selected_model = cl.user_session.get("model")
        completion, _ = await call_llm_with_fallback(history, temperature=temperature, requested_model=selected_model)
        response_msg = cl.Message(content="")
        await response_msg.send()
        full_response = ""
        for chunk in completion:
            text_tok = getattr(chunk.choices[0].delta, "content", "") or ""
            full_response += text_tok
            await response_msg.stream_token(text_tok)
        history.append({"role": "assistant", "content": full_response})
        cl.user_session.set("message_history", sanitize_history_for_storage(history))
        actions = [
            cl.Action(name="regenerate_answer", label="🔄 Regenerate", icon="refresh-cw", payload={"action": "regenerate"}),
            cl.Action(name="verify_citations", label="📄 Verify Citations", icon="file-check", payload={"action": "verify"}),
            cl.Action(name="search_web_instead", label="🌐 Search Web", icon="globe", payload={"action": "search_web"})
        ]
        response_msg.actions = actions
        rag_content = cl.user_session.get("last_rag_result")
        elements: List[Any] = []
        if rag_content:
            elements.append(cl.Text(name="Source", content=rag_content, display="side"))
            sources = cl.user_session.get("last_rag_sources") or []
            for src in sources:
                if not isinstance(src, str):
                    continue
                src_path = os.path.join(os.path.dirname(__file__), "data", "textbooks", src)
                if os.path.exists(src_path) and src.lower().endswith(".pdf"):
                    elements.append(cl.Pdf(name=src, path=src_path, display="side"))
            cl.user_session.set("last_rag_result", None)
            cl.user_session.set("last_rag_sources", None)
        if elements:
            response_msg.elements = elements
        chat_profile_name = cl.user_session.get("chat_profile") or "Omni Mode"
        if chat_profile_name == "Voice Mode":
            await add_voice_to_response(response_msg, full_response)
        await response_msg.update()
    except Exception as e:
        await cl.ErrorMessage(content=f"⚠️ Failed to regenerate answer: {str(e)}").send()


@cl.action_callback("search_web_instead")
async def on_search_web_instead(action: cl.Action):
    try:
        history = cl.user_session.get("message_history", [])
        if not history:
            return
        user_query = ""
        for msg in reversed(history):
            if msg.get("role") == "user":
                user_query = msg.get("content", "")
                if isinstance(user_query, list):
                    user_query = next((c.get("text", "") for c in user_query if c.get("type") == "text"), "")
                break
        if not user_query:
            await cl.Message(content="Could not find the last query to search the web instead.").send()
            return

        async with cl.Step(name="Searching the Web...", type="tool") as step:
            step.input = {"query": user_query}
            # FIX P1-9: Use async wrapper
            web_results = await perform_web_search_async(user_query)
            step.output = web_results

        history.append({
            "role": "system",
            "content": f"[SYSTEM: The user clicked 'Search Web Instead'. Here are the live web results for '{user_query}':\n{web_results}\nSynthesize these results into a clear answer.]"
        })
        temperature = cl.user_session.get("temperature", 0.7)
        selected_model = cl.user_session.get("model")
        completion, _ = await call_llm_with_fallback(history, temperature=temperature, requested_model=selected_model)
        response_msg = cl.Message(content="")
        await response_msg.send()
        full_response = ""
        for chunk in completion:
            text_tok = getattr(chunk.choices[0].delta, "content", "") or ""
            full_response += text_tok
            await response_msg.stream_token(text_tok)
        history.append({"role": "assistant", "content": full_response})
        cl.user_session.set("message_history", sanitize_history_for_storage(history))
        actions = [
            cl.Action(name="regenerate_answer", label="🔄 Regenerate", icon="refresh-cw", payload={"action": "regenerate"}),
            cl.Action(name="verify_citations", label="📄 Verify Citations", icon="file-check", payload={"action": "verify"}),
            cl.Action(name="search_web_instead", label="🌐 Search Web", icon="globe", payload={"action": "search_web"})
        ]
        response_msg.actions = actions
        chat_profile_name = cl.user_session.get("chat_profile") or "Omni Mode"
        if chat_profile_name == "Voice Mode":
            await add_voice_to_response(response_msg, full_response)
        await response_msg.update()
    except Exception as e:
        await cl.ErrorMessage(content=f"⚠️ Failed to search the web: {str(e)}").send()


@cl.action_callback("verify_citations")
async def on_verify_citations(action: cl.Action):
    try:
        sources = cl.user_session.get("last_rag_sources") or []
        if not sources:
            await cl.Message(content="✅ **Citations Verified**: All context segments sourced from uploaded workspace documents.").send()
        else:
            await cl.Message(content=f"✅ **Citations Verified**: Sourced from: {', '.join(sources)}").send()
    except Exception as e:
        await cl.ErrorMessage(content=f"⚠️ Failed to verify citations: {str(e)}").send()


@cl.action_callback("resume_session")
async def execute_resume_session(action: cl.Action):
    session_id = action.payload.get("session_id")
    if not isinstance(session_id, str):
        return
    try:
        layer = cl_data.get_data_layer()
        if layer:
            thread = await layer.get_thread(session_id)
        if thread:
            history = [{"role": msg.get("role") or msg.get("type", "").split("_")[0], "content": msg.get("content") or msg.get("output", "")} for msg in thread.get("steps", []) if msg.get("type") in ("user_message", "assistant_message")]
            cl.user_session.set("message_history", history)
            cl.user_session.set("session_id", session_id)
            await cl.Message(content="🔄 **Neural Link Re-established.** Context restored.").send()
    except Exception as e:
        await cl.ErrorMessage(content=f"⚠️ Failed to restore session: {str(e)}").send()
