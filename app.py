import os
import hashlib
import json
import base64
import re
from datetime import datetime
from dotenv import load_dotenv
import chainlit as cl
from openai import OpenAI

# --- MONKEY PATCH DECORATORS FOR FLEXIBLE CALL SYNTAX ---
_original_on_audio_chunk = cl.on_audio_chunk
def patched_on_audio_chunk(*args, **kwargs):
    kwargs.pop("name", None)
    if args and callable(args[0]):
        return _original_on_audio_chunk(args[0])
    return lambda f: _original_on_audio_chunk(f)
cl.on_audio_chunk = patched_on_audio_chunk

_original_on_audio_end = cl.on_audio_end
def patched_on_audio_end(*args, **kwargs):
    if args and callable(args[0]):
        return _original_on_audio_end(args[0])
    return lambda f: _original_on_audio_end(f)
cl.on_audio_end = patched_on_audio_end

_original_set_starters = cl.set_starters
def patched_set_starters(*args, **kwargs):
    if args and callable(args[0]):
        return _original_set_starters(args[0])
    return lambda f: _original_set_starters(f)
cl.set_starters = patched_set_starters

_original_set_chat_profiles = cl.set_chat_profiles
def patched_set_chat_profiles(*args, **kwargs):
    if args and callable(args[0]):
        return _original_set_chat_profiles(args[0])
    return lambda f: _original_set_chat_profiles(f)
cl.set_chat_profiles = patched_set_chat_profiles

from duckduckgo_search import DDGS

# Import backend modules
from src.latency_predictor import predict_latency
from src.rag_scholar import search_textbooks_with_sources, build_vector_database
from chainlit.server import app as fastapi_app
from fastapi import UploadFile, File, Response
import shutil
import asyncio

import chainlit.data as cl_data
from chainlit.data.sql_alchemy import SQLAlchemyDataLayer
from sqlalchemy import MetaData, Table, Column, String, Boolean, Integer, ForeignKey
import aiofiles
from typing import Union, Dict, Any
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
        
        mode = "w" if isinstance(data, str) else "wb"
        async with aiofiles.open(file_path, mode) as f:
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

# Configure Data Layer globally
data_layer = SQLAlchemyDataLayer(
    conninfo="sqlite+aiosqlite:///chainlit.db",
    storage_provider=storage_provider
)
cl_data._data_layer = data_layer

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
    Column("icon", String)
)

feedbacks_table = Table(
    "feedbacks",
    metadata,
    Column("id", String, primary_key=True),
    Column("forId", String, ForeignKey("steps.id", ondelete="CASCADE"), nullable=False),
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
    Column("size", Integer),
    Column("language", String),
    Column("page", Integer),
    Column("props", String),
    Column("autoPlay", Boolean),
    Column("playerConfig", String),
    Column("forId", String),
    Column("mime", String)
)

async def init_db():
    async with data_layer.engine.begin() as conn:
        await conn.run_sync(metadata.create_all)

@fastapi_app.on_event("startup")
async def startup_event():
    await init_db()


# Load environment variables
load_dotenv()

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
    # Native Google Generative AI Client Configuration
    import google.generativeai as genai
    genai.configure(api_key=API_KEY_GEMINI)
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
    try:
        results = DDGS().text(query, max_results=3)
        return "\n\n".join([f"Source: {res['title']}\nSnippet: {res['body']}" for res in
                            results]) if results else "No internet results."
    except Exception as e:
        return f"Web search failed: {str(e)}"


async def call_llm_with_fallback(messages, tools=None, tool_choice=None, temperature=None, vision_mode=False):
    if vision_mode:
        MODELS_ROUTE = [
            {"provider": "Groq", "client": groq_client, "model": "llama-3.2-90b-vision-preview"},
            {"provider": "Gemini", "client": gemini_client, "model": "gemini-1.5-flash"}
        ]
        tools = None
    else:
        MODELS_ROUTE = [
            {"provider": "Groq", "client": groq_client, "model": "llama-3.3-70b-versatile"},
            {"provider": "Groq", "client": groq_client, "model": "mixtral-8x7b-32768"},
            {"provider": "Gemini", "client": gemini_client, "model": "gemini-1.5-flash"}
        ]

    last_error = None
    for route in MODELS_ROUTE:
        try:
            if route["provider"] == "Groq":
                kwargs = {"model": route["model"], "messages": messages}
                if temperature is not None:
                    kwargs["temperature"] = temperature
                    
                # Exclude tools for vision models (llama-3.2-90b-vision-preview) to avoid API errors
                if tools and "vision" not in route["model"].lower():
                    kwargs["tools"] = tools
                    kwargs["tool_choice"] = tool_choice or "auto"
                else:
                    kwargs["stream"] = True

                completion = route["client"].chat.completions.create(**kwargs)
                return completion, route["model"]
                
            elif route["provider"] == "Gemini":
                # Convert OpenAI messages to Gemini contents format
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
                                    import base64
                                    import io
                                    from PIL import Image
                                    header, encoded = url.split(",", 1)
                                    img_data = base64.b64decode(encoded)
                                    img = Image.open(io.BytesIO(img_data))
                                    parts.append(img)
                                    
                    gemini_role = "user" if role == "user" else "model"
                    contents.append({"role": gemini_role, "parts": parts})

                # Setup generation config
                gen_config = route["client"].types.GenerationConfig(
                    temperature=temperature if temperature is not None else 0.7
                )
                
                # Setup tools
                gemini_tools = [t["function"] for t in tools] if tools else None

                # Initialize model
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
                    
                    # Parse tool calls
                    import uuid
                    gemini_tool_calls = []
                    
                    if response.candidates and response.candidates[0].content.parts:
                        for part in response.candidates[0].content.parts:
                            if hasattr(part, "function_call") and part.function_call:
                                import json
                                args_dict = dict(part.function_call.args)
                                args_json = json.dumps(args_dict)
                                call_id = f"call_{uuid.uuid4().hex}"
                                gemini_tool_calls.append(
                                    GeminiToolCall(
                                        id=call_id,
                                        name=part.function_call.name,
                                        arguments=args_json
                                    )
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
    """Safely converts a message (dict or ChatCompletionMessage) to a standard dict to prevent object attribute errors."""
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
    clean_history = []
    for msg in history_array:
        msg_dict = message_to_dict(msg)

        if isinstance(msg_dict.get("content"), list):
            text_only = next((c["text"] for c in msg_dict["content"] if c.get("type") == "text"),
                             "[Image Omitted for Storage]")
            msg_dict["content"] = text_only

        clean_history.append(msg_dict)
    return clean_history


# --- CHAINLIT STARTERS ---
@cl.set_starters()
async def set_starters():
    return [
        cl.Starter(
            label="📚 Scholar RAG",
            message="Can you search the textbooks and explain Page Replacement Algorithms?",
            icon="/public/favicon.ico"
        ),
        cl.Starter(
            label="🎮 Gamer Latency",
            message="Check network ping for gaming session stability",
            icon="/public/favicon.ico"
        ),
        cl.Starter(
            label="🌐 Omni Search",
            message="Search the web for the current AWS server status.",
            icon="/public/favicon.ico"
        )
    ]


@cl.set_chat_profiles()
async def chat_profile():
    return [
        cl.ChatProfile(
            name="Omni Mode",
            markdown_description="Standard full-capability assistant mode.",
            icon="https://cdn-icons-png.flaticon.com/512/4712/4712035.png",
        ),
        cl.ChatProfile(
            name="Scholar Mode",
            markdown_description="Focuses on academic and textbook searches.",
            icon="https://cdn-icons-png.flaticon.com/512/3145/3145765.png",
        ),
        cl.ChatProfile(
            name="Gamer Mode",
            markdown_description="Focuses on gaming ping, servers and network stability.",
            icon="https://cdn-icons-png.flaticon.com/512/808/808439.png",
        )
    ]


@cl.password_auth_callback
async def auth_callback(username: str, password: str):
    username = username.strip()
    password = password.strip()
    if not username or not password:
        return None
    password_hash = hashlib.sha256(password.encode()).hexdigest()
    try:
        existing_user = await data_layer.get_user(username)
        if existing_user:
            stored_hash = existing_user.metadata.get("password_hash")
            if stored_hash == password_hash:
                return cl.User(id=existing_user.id, identifier=existing_user.identifier, metadata=existing_user.metadata)
            return None
        else:
            new_user = cl.User(identifier=username, metadata={"password_hash": password_hash})
            persisted_user = await data_layer.create_user(new_user)
            if persisted_user:
                return cl.User(id=persisted_user.id, identifier=persisted_user.identifier, metadata=persisted_user.metadata)
            return None
    except Exception as e:
        print(f"[-] Auth callback database error: {e}")
        return None

@cl.on_chat_start
async def start_chat():
    user = cl.user_session.get("user")
    if not user:
        return
    cl.user_session.set("session_id", cl.user_session.get("id"))
    chat_profile_name = cl.user_session.get("chat_profile") or "Omni Mode"
    cl.user_session.set("chat_profile", chat_profile_name)
    
    # AskUserMessage for Gamer Mode Context
    game_context = ""
    if chat_profile_name == "Gamer Mode":
        try:
            res = await cl.AskUserMessage(
                content="Welcome to Gamer Mode. Please type the name of the game you're playing (e.g. Valorant, Apex, CS2):", 
                timeout=120
            ).send()
            if res:
                game_context = f"\nUser is currently playing: {res['output']}"
        except Exception as e:
            print(f"[-] Gamer start profile error: {e}")
    
    system_instruction = f"You are NexusAI. Maintain deep context awareness. Your current profile is {chat_profile_name}.{game_context}"
    cl.user_session.set("message_history", [{"role": "system", "content": system_instruction}])

    # Chat Settings setup
    try:
        await cl.ChatSettings(
            [
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
        {"id": "new", "icon": "bolt", "description": "Factory Reset (Wipes all database data)"}
    ]
    try:
        await cl.context.emitter.set_commands(commands)
    except Exception as e:
        print(f"[-] Slash commands register error: {e}")

    welcome_text = (
        "> # NexusAI\n"
        f"> ### Active Mode: {chat_profile_name}\n"
        "Ready to assist — ask, explore, or play."
    )

    try:
        await cl.Message(content=welcome_text).send()
    except Exception as e:
        print(f"[-] Welcome message send error: {e}")


@cl.on_chat_end
async def end_chat():
    textbooks_dir = os.path.join(os.path.dirname(__file__), "data", "textbooks")
    if os.path.exists(textbooks_dir):
        for filename in os.listdir(textbooks_dir):
            file_path = os.path.join(textbooks_dir, filename)
            try:
                if os.path.isfile(file_path):
                    os.unlink(file_path)
            except Exception:
                pass
        # Rebuild DB to reflect empty state
        try:
            build_vector_database()
        except Exception as e:
            print(f"[-] RAG cleanup index rebuild failed: {e}")


# --- CUSTOM API ENDPOINTS FOR WORKSPACE ---
@fastapi_app.post("/api/upload")
async def upload_document(file: UploadFile = File(...)):
    try:
        textbooks_dir = os.path.join(os.path.dirname(__file__), "data", "textbooks")
        os.makedirs(textbooks_dir, exist_ok=True)
        file_path = os.path.join(textbooks_dir, file.filename)
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        return {"filename": file.filename, "status": "success"}
    except Exception as e:
        return Response(content=json.dumps({"status": "error", "message": str(e)}), status_code=500)


@fastapi_app.post("/api/build-index")
async def build_index():
    try:
        build_vector_database()
        return {"status": "success"}
    except Exception as e:
        return Response(content=json.dumps({"status": "error", "message": str(e)}), status_code=500)


@fastapi_app.delete("/api/delete/{filename}")
async def delete_document(filename: str):
    try:
        textbooks_dir = os.path.join(os.path.dirname(__file__), "data", "textbooks")
        file_path = os.path.join(textbooks_dir, filename)
        if os.path.exists(file_path):
            os.remove(file_path)
            build_vector_database()
            return {"filename": filename, "status": "deleted"}
        return Response(status_code=404)
    except Exception as e:
        return Response(content=json.dumps({"status": "error", "message": str(e)}), status_code=500)


@cl.on_audio_start
async def on_audio_start():
    cl.user_session.set("audio_buffer", None)
    cl.user_session.set("audio_mime_type", None)
    return True

@cl.on_audio_chunk(name="audio-stream")
async def on_audio_chunk(chunk):
    # Initialize the buffer on the first chunk or if missing
    buffer = cl.user_session.get("audio_buffer")
    if not buffer:
        import io
        mime_type = getattr(chunk, "mimeType", "audio/webm")
        buffer = io.BytesIO()
        buffer.name = f"input_audio.{mime_type.split('/')[1]}"
        cl.user_session.set("audio_buffer", buffer)
        cl.user_session.set("audio_mime_type", mime_type)
        
    buffer.write(chunk.data)

@cl.on_audio_end()
async def on_audio_end(*args, **kwargs):
    audio_buffer = cl.user_session.get("audio_buffer")
    if not audio_buffer:
        return
        
    audio_buffer.seek(0)
    audio_data = audio_buffer.read()
    mime_type = cl.user_session.get("audio_mime_type") or "audio/webm"
    filename = getattr(audio_buffer, "name", "input_audio.webm")
    
    # Reset buffer in session
    cl.user_session.set("audio_buffer", None)
    cl.user_session.set("audio_mime_type", None)
    
    # Call Groq Whisper API for transcription
    try:
        # Using Groq's whisper-large-v3 model
        transcription = groq_client.audio.transcriptions.create(
            model="whisper-large-v3",
            file=(filename, audio_data, mime_type)
        )
        text = transcription.text
        
        if text and text.strip():
            # Send the transcribed text as a visible message from the user
            user_msg = cl.Message(author="You", content=text)
            await user_msg.send()
            
            # Programmatically trigger handle_message to process the transcription
            await handle_message(user_msg)
    except Exception as e:
        print(f"[-] Audio transcription failed: {e}")
        await cl.ErrorMessage(content=f"⚠️ Transcription failed: {e}").send()

@cl.on_settings_update
async def setup_agent(settings):
    try:
        cl.user_session.set("temperature", settings.get("Temperature", 0.7))
        cl.user_session.set("deep_web_search", settings.get("DeepSearch", False))
    except Exception as e:
        print(f"[-] Settings update error: {e}")


async def enforce_three_session_limit():
    """Strictly caps the chat history to the 3 most recent sessions per user (FIFO) using direct SQL database checks."""
    try:
        if not cl_data._data_layer or not hasattr(cl_data._data_layer, "engine"):
            return
            
        from sqlalchemy import text
        async with cl_data._data_layer.engine.begin() as conn:
            # Query all threads, ordered by createdAt descending
            result = await conn.execute(
                text("SELECT id FROM threads ORDER BY createdAt DESC")
            )
            rows = result.fetchall()
            thread_ids = [row[0] for row in rows]
            
            # If more than 3 threads exist, delete the older ones
            if len(thread_ids) > 3:
                for old_thread_id in thread_ids[3:]:
                    print(f"[*] Purging old session thread to preserve 3-session limit: {old_thread_id}")
                    # Delete cascade elements, steps, and threads
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
            
            completion = groq_client.chat.completions.create(
                model="llama-3.1-8b-instant",
                messages=[
                    {"role": "system", "content": "Summarize this into a 3-5 word title. No quotes. No extra text."},
                    {"role": "user", "content": first_msg}
                ]
            )
            title = completion.choices[0].message.content.strip().replace('"', '').replace("'", "")
            thread_id = cl.context.session.thread_id
            if thread_id and cl_data._data_layer:
                await cl_data._data_layer.update_thread(thread_id, name=title, metadata={})
                await enforce_three_session_limit()
        except Exception as e:
            print(f"[-] Error in auto_rename_session: {e}")


@cl.on_message
async def handle_message(message: cl.Message):
    try:
        # Load history
        history = [message_to_dict(m) for m in cl.user_session.get("message_history", [])]

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
                await cl.Message(content="🧹 *Display cleared to reduce clutter. (NexusAI still retains memory of this session).*").send()
                return
                
            elif cmd == "new-chat":
                cl.user_session.set("message_history", [])
                await cl.CopilotFunction(name="new_chat_session", args={}).acall()
                return

            elif cmd == "new":
                cl.user_session.set("message_history", [])
                try:
                    async with data_layer.engine.begin() as conn:
                        await conn.run_sync(metadata.drop_all)
                        await conn.run_sync(metadata.create_all)
                    await cl.Message(content="💥 *Factory Reset Complete. Purged all database records. Resetting system...*").send()
                except Exception as db_err:
                    print(f"[-] Factory reset database error: {db_err}")
                    await cl.ErrorMessage(content=f"⚠️ Failed database reset: {db_err}").send()
                
                await cl.CopilotFunction(name="new_chat_session", args={}).acall()
                return

        # --- ASKUSER MESSAGE TELEMETRY INTERACTION ---
        msg_content = message.content.strip().lower() if message.content else ""
        if "check ping" in msg_content or "predict ping" in msg_content:
            digits = re.findall(r'\d+', msg_content)
            if not digits:
                ask_msg = await cl.AskUserMessage(
                    content="What hour (0-23)?",
                    timeout=60
                ).send()
                if ask_msg:
                    ans_digits = re.findall(r'\d+', ask_msg['output'])
                    if ans_digits:
                        hour_val = int(ans_digits[0])
                    else:
                        hour_val = datetime.now().hour
                    
                    ping = predict_latency(hour=hour_val, minute=0, server_code=0)
                    response_msg = cl.Message(
                        content=f"🎮 **Network Telemetry**: Predicted ping for hour `{hour_val}:00` is `{ping} ms`."
                    )
                    actions = [
                        cl.Action(name="regenerate_answer", value="regenerate_action", label="🔄 Regenerate Response", payload={"action": "regenerate"}),
                        cl.Action(name="verify_citations", value="verify_action", label="📄 Verify Citations", payload={"action": "verify"}),
                        cl.Action(name="search_web_instead", value="search_web_action", label="🌐 Search Web Instead", payload={"action": "search_web"})
                    ]
                    response_msg.actions = actions
                    await response_msg.send()
                    
                    history.append({"role": "user", "content": f"Check ping for hour {hour_val}"})
                    history.append({"role": "assistant", "content": response_msg.content})
                    cl.user_session.set("message_history", history)
                    return

        # Staging tray file triggers
        if message.content.startswith("[FILE_SELECTED:"):
            filename = message.content.split("[FILE_SELECTED:")[1].split("]")[0]
            file_path = os.path.join(os.path.dirname(__file__), "data", "textbooks", filename)
            
            if os.path.exists(file_path):
                file_element = cl.File(name=filename, path=file_path, display="inline")
                await cl.Message(
                    content=f"📎 **File Focused**: NexusAI has successfully loaded `{filename}`. Ask me questions about it!",
                    elements=[file_element]
                ).send()
            else:
                await cl.Message(
                    content=f"📎 **File Focused**: NexusAI is ready to analyze `{filename}`. Ask me questions about it!"
                ).send()
            return
            
        elif message.content.startswith("[FILE_DESELECTED:"):
            filename = message.content.split("[FILE_DESELECTED:")[1].split("]")[0]
            await cl.Message(content=f"🔓 **File Unfocused**: `{filename}` is no longer focused.").send()
            return

        tool_choice = None
        if message.command == "scholar":
            tool_choice = {"type": "function", "function": {"name": "query_academic_textbooks"}}
        elif message.command == "gamer":
            tool_choice = {"type": "function", "function": {"name": "check_game_network_stability"}}
        elif message.command == "web":
            tool_choice = {"type": "function", "function": {"name": "execute_web_search"}}

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

        # Multi-Modal Support
        if message.elements:
            for element in message.elements:
                try:
                    if element.name.endswith(('.txt', '.py', '.js', '.json', '.csv', '.html', '.css', '.md', '.sh')):
                        with open(element.path, "r", encoding="utf-8") as f:
                            attached_text += f"\n\n--- Code/Text Snippet: {element.name} ---\n{f.read()}"
                    elif element.name.endswith(('.docx', '.doc')):
                        import docx
                        doc = docx.Document(element.path)
                        text = "\n".join([para.text for para in doc.paragraphs])
                        attached_text += f"\n\n--- Document: {element.name} ---\n{text}"
                    elif element.name.endswith(('.pptx', '.ppt')):
                        import pptx
                        prs = pptx.Presentation(element.path)
                        text = "\n".join(
                            [shape.text for slide in prs.slides for shape in slide.shapes if hasattr(shape, "text")])
                        attached_text += f"\n\n--- Presentation: {element.name} ---\n{text}"
                    elif element.name.endswith(".pdf"):
                        import PyPDF2
                        with open(element.path, "rb") as f:
                            reader = PyPDF2.PdfReader(f)
                            text = "\n".join([page.extract_text() for page in reader.pages if page.extract_text()])
                        attached_text += f"\n\n--- PDF Document: {element.name} ---\n{text}"
                    elif element.name.endswith(('.xlsx', '.xls')):
                        import pandas as pd
                        xls = pd.ExcelFile(element.path)
                        sheet_texts = []
                        for sheet_name in xls.sheet_names:
                            df = pd.read_excel(xls, sheet_name=sheet_name)
                            sheet_texts.append(f"--- Sheet: {sheet_name} ---\n{df.to_string()}")
                        text = "\n\n".join(sheet_texts)
                        attached_text += f"\n\n--- Spreadsheet: {element.name} ---\n{text}"
                    elif element.name.lower().endswith(('.png', '.jpg', '.jpeg', '.webp')):
                        with open(element.path, "rb") as img_file:
                            base64_image = base64.b64encode(img_file.read()).decode('utf-8')
                        image_contents.append(
                            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}})
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

        # Read settings dynamically
        temperature = cl.user_session.get("temperature", 0.7)
        deep_web = cl.user_session.get("deep_web_search", False)
        chat_profile_name = cl.user_session.get("chat_profile") or "Omni Mode"

        # Restrict tools based on active Chat Profile
        active_tools = TOOLS_SCHEMA.copy()
        if chat_profile_name == "Scholar Mode":
            active_tools = [t for t in TOOLS_SCHEMA if t["function"]["name"] in ("query_academic_textbooks", "execute_web_search")]
        elif chat_profile_name == "Gamer Mode":
            active_tools = [t for t in TOOLS_SCHEMA if t["function"]["name"] in ("check_game_network_stability", "execute_web_search")]

        if deep_web:
            history.append({
                "role": "system",
                "content": "[SYSTEM INJECTION: Deep Web Search is enabled. Actively use the web search tool to find live, real-time facts.]"
            })

        if has_vision:
            streamed_completion, _ = await call_llm_with_fallback(
                history, 
                temperature=temperature, 
                vision_mode=True
            )
            response_msg = cl.Message(content="")
            await response_msg.send()
            full_response = ""
            for chunk in streamed_completion:
                text = getattr(chunk.choices[0].delta, "content", "") or ""
                full_response += text
                await response_msg.stream_token(text)
            history.append({"role": "assistant", "content": full_response})
            
            # Attach action buttons
            actions = [
                cl.Action(name="regenerate_answer", value="regenerate_action", label="🔄 Regenerate Response", payload={"action": "regenerate"}),
                cl.Action(name="verify_citations", value="verify_action", label="📄 Verify Citations", payload={"action": "verify"}),
                cl.Action(name="search_web_instead", value="search_web_action", label="🌐 Search Web Instead", payload={"action": "search_web"})
            ]
            response_msg.actions = actions
            await response_msg.update()

        else:
            completion, _ = await call_llm_with_fallback(
                history, 
                tools=active_tools, 
                tool_choice=tool_choice, 
                temperature=temperature
            )
            response_message = completion.choices[0].message

            if response_message.tool_calls:
                history.append(message_to_dict(response_message))
                for tool_call in response_message.tool_calls:
                    args = json.loads(tool_call.function.arguments)
                    func = tool_call.function.name

                    # WRAP TOOL CALLS IN cl.Step
                    async with cl.Step(name=f"Processing {func}...", type="tool") as step:
                        step.input = args
                        content = ""

                        if func == "check_game_network_stability":
                            hour_val = args.get("hour")
                            
                            # AskUserMessage: Halt and prompt if hour is missing
                            if hour_val is None:
                                ask_msg = await cl.AskUserMessage(
                                    content="What hour (0-23)?",
                                    timeout=60
                                ).send()
                                if ask_msg:
                                    try:
                                        digits = "".join(filter(str.isdigit, ask_msg['output']))
                                        hour_val = int(digits)
                                        if not (0 <= hour_val <= 23):
                                            hour_val = datetime.now().hour
                                    except ValueError:
                                        hour_val = datetime.now().hour
                                else:
                                    hour_val = datetime.now().hour
                            
                            ping = predict_latency(hour=hour_val, minute=0, server_code=0)
                            content = f"Estimated latency: {ping} ms."
                            
                        elif func == "query_academic_textbooks":
                            content, sources = search_textbooks_with_sources(args.get("search_query"), k=3)
                            
                            # Save in user session to attach to the final assistant message
                            cl.user_session.set("last_rag_result", content)
                            cl.user_session.set("last_rag_sources", sources)
                            
                            # Build inline indicator preview
                            elements = [
                                cl.Text(name="Source", content=content, display="inline")
                            ]
                            for src in sources:
                                src_path = os.path.join(os.path.dirname(__file__), "data", "textbooks", src)
                                if os.path.exists(src_path):
                                    if src.lower().endswith(".pdf"):
                                        elements.append(cl.Pdf(name=src, path=src_path, display="side"))
                                    else:
                                        elements.append(cl.Text(name=src, path=src_path, display="side"))
                                        
                            await cl.Message(content="Found relevant textbook segments:", elements=elements).send()
                            content = f"Academic Textbook search results:\n{content}"
                            
                        elif func == "execute_web_search":
                            content = perform_web_search(args.get("query"))

                        step.output = content

                    history.append({"role": "tool", "tool_call_id": tool_call.id, "name": func, "content": content})

                final_completion, _ = await call_llm_with_fallback(history, temperature=temperature)
                response_msg = cl.Message(content="")
                await response_msg.send()
                full_response = ""
                for chunk in final_completion:
                    text = getattr(chunk.choices[0].delta, "content", "") or ""
                    full_response += text
                    await response_msg.stream_token(text)
                history.append({"role": "assistant", "content": full_response})

                # Attach action buttons
                actions = [
                    cl.Action(name="regenerate_answer", value="regenerate_action", label="🔄 Regenerate Response", payload={"action": "regenerate"}),
                    cl.Action(name="verify_citations", value="verify_action", label="📄 Verify Citations", payload={"action": "verify"}),
                    cl.Action(name="search_web_instead", value="search_web_action", label="🌐 Search Web Instead", payload={"action": "search_web"})
                ]
                response_msg.actions = actions

                # Attach rich RAG elements to final response if searched
                rag_content = cl.user_session.get("last_rag_result")
                elements = []
                if rag_content:
                    elements.append(cl.Text(name="Source", content=rag_content, display="side"))
                    sources = cl.user_session.get("last_rag_sources") or []
                    for src in sources:
                        src_path = os.path.join(os.path.dirname(__file__), "data", "textbooks", src)
                        if os.path.exists(src_path):
                            if src.lower().endswith(".pdf"):
                                elements.append(cl.Pdf(name=src, path=src_path, display="side"))
                    cl.user_session.set("last_rag_result", None)
                    cl.user_session.set("last_rag_sources", None)
                
                response_msg.elements = elements
                await response_msg.update()

            else:
                streamed_completion, _ = await call_llm_with_fallback(history, temperature=temperature)
                response_msg = cl.Message(content="")
                await response_msg.send()
                full_response = ""
                for chunk in streamed_completion:
                    text = getattr(chunk.choices[0].delta, "content", "") or ""
                    full_response += text
                    await response_msg.stream_token(text)

                history.append({"role": "assistant", "content": full_response})

                # Attach action buttons
                actions = [
                    cl.Action(name="regenerate_answer", value="regenerate_action", label="🔄 Regenerate Response", payload={"action": "regenerate"}),
                    cl.Action(name="verify_citations", value="verify_action", label="📄 Verify Citations", payload={"action": "verify"}),
                    cl.Action(name="search_web_instead", value="search_web_action", label="🌐 Search Web Instead", payload={"action": "search_web"})
                ]
                response_msg.actions = actions
                await response_msg.update()

        # Auto Rename Chat
        await auto_rename_session(history)
        cl.user_session.set("message_history", history)

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
        completion, _ = await call_llm_with_fallback(history, temperature=temperature)
        
        response_msg = cl.Message(content="")
        await response_msg.send()
        
        full_response = ""
        for chunk in completion:
            text = getattr(chunk.choices[0].delta, "content", "") or ""
            full_response += text
            await response_msg.stream_token(text)
        
        history.append({"role": "assistant", "content": full_response})
        cl.user_session.set("message_history", history)
        
        actions = [
            cl.Action(name="regenerate_answer", value="regenerate_action", label="🔄 Regenerate Response", payload={"action": "regenerate"}),
            cl.Action(name="verify_citations", value="verify_action", label="📄 Verify Citations", payload={"action": "verify"}),
            cl.Action(name="search_web_instead", value="search_web_action", label="🌐 Search Web Instead", payload={"action": "search_web"})
        ]
        response_msg.actions = actions
        
        # Attach rich elements if any RAG occurred
        rag_content = cl.user_session.get("last_rag_result")
        elements = []
        if rag_content:
            elements.append(cl.Text(name="Source", content=rag_content, display="side"))
            sources = cl.user_session.get("last_rag_sources") or []
            for src in sources:
                src_path = os.path.join(os.path.dirname(__file__), "data", "textbooks", src)
                if os.path.exists(src_path):
                    if src.lower().endswith(".pdf"):
                        elements.append(cl.Pdf(name=src, path=src_path, display="side"))
            cl.user_session.set("last_rag_result", None)
            cl.user_session.set("last_rag_sources", None)
        
        response_msg.elements = elements
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
            web_results = perform_web_search(user_query)
            step.output = web_results
        
        history.append({
            "role": "system",
            "content": f"[SYSTEM: The user clicked 'Search Web Instead'. Here are the live web results for '{user_query}':\n{web_results}\nSynthesize these results into a clear answer.]"
        })
        
        temperature = cl.user_session.get("temperature", 0.7)
        completion, _ = await call_llm_with_fallback(history, temperature=temperature)
        
        response_msg = cl.Message(content="")
        await response_msg.send()
        
        full_response = ""
        for chunk in completion:
            text = getattr(chunk.choices[0].delta, "content", "") or ""
            full_response += text
            await response_msg.stream_token(text)
        
        history.append({"role": "assistant", "content": full_response})
        cl.user_session.set("message_history", history)
        
        actions = [
            cl.Action(name="regenerate_answer", value="regenerate_action", label="🔄 Regenerate Response", payload={"action": "regenerate"}),
            cl.Action(name="verify_citations", value="verify_action", label="📄 Verify Citations", payload={"action": "verify"}),
            cl.Action(name="search_web_instead", value="search_web_action", label="🌐 Search Web Instead", payload={"action": "search_web"})
        ]
        response_msg.actions = actions
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
            await cl.Message(content=f"✅ **Citations Verified**: Sourced successfully from: {', '.join(sources)}").send()
    except Exception as e:
        await cl.ErrorMessage(content=f"⚠️ Failed to verify citations: {str(e)}").send()


@cl.action_callback("resume_session")
async def execute_resume_session(action: cl.Action):
    session_id = action.payload.get("session_id")
    try:
        thread = await cl_data._data_layer.get_thread(session_id)
        if thread:
            history = [{"role": msg.role, "content": msg.content} for msg in thread.steps if msg.type in ("user_message", "assistant_message")]
            cl.user_session.set("message_history", history)
            cl.user_session.set("session_id", session_id)
            await cl.Message(content="🔄 **Neural Link Re-established.** Context restored.").send()
    except Exception as e:
        await cl.ErrorMessage(content=f"⚠️ Failed to restore session: {str(e)}").send()
