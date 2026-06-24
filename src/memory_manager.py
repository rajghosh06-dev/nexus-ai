import os
import json

BASE_DIR = os.path.dirname(os.path.dirname(__file__))
PROFILE_FILE = os.path.join(BASE_DIR, "data", "user_profile.json")


def load_user_profile():
    """Loads the long-term user profile facts and chat history from disk."""
    if not os.path.exists(os.path.dirname(PROFILE_FILE)):
        os.makedirs(os.path.dirname(PROFILE_FILE))

    if not os.path.exists(PROFILE_FILE):
        default_profile = {
            "name": "Local User",
            "recent_chats": []  # Initialize the empty FIFO Queue
        }
        with open(PROFILE_FILE, 'w') as f:
            json.dump(default_profile, f, indent=4)
        return default_profile

    try:
        with open(PROFILE_FILE, 'r') as f:
            data = json.load(f)
            # Ensure older profiles get the queue initialized
            if "recent_chats" not in data:
                data["recent_chats"] = []
            return data
    except Exception:
        return {"recent_chats": []}


def save_chat_session(session_id, history_array):
    """Saves the chat history, strictly keeping at most the last 3 sessions (FIFO)."""
    profile = load_user_profile()

    # Check if we are updating a session that is already in the queue
    existing_index = next((i for i, chat in enumerate(profile["recent_chats"]) if chat["session_id"] == session_id),
                          None)

    # Generate a smart preview title from the user's first prompt
    preview = "New Empty Chat"
    for msg in history_array:
        if msg.get("role") == "user":
            preview = msg.get("content", "")[:35] + "..."
            break

    chat_data = {
        "session_id": session_id,
        "preview": preview,
        "messages": history_array
    }

    if existing_index is not None:
        # Update current chat
        profile["recent_chats"][existing_index] = chat_data
    else:
        # Append new chat
        profile["recent_chats"].append(chat_data)
        # FIFO Dequeue: If queue exceeds 3, pop out the oldest (index 0)
        if len(profile["recent_chats"]) > 3:
            profile["recent_chats"].pop(0)

    with open(PROFILE_FILE, 'w') as f:
        json.dump(profile, f, indent=4)