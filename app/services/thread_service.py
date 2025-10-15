import os
import json
import hashlib
import uuid
from pathlib import Path
from utils.yaml_utils import load_yaml, save_yaml


# === Helper functions ===

def _ensure_dir(path):
    Path(path).parent.mkdir(parents=True, exist_ok=True)


def get_user_shortid(session):
    """Generate a short unique hash for the user or anonymous session."""
    token = session.get("id_token")
    if token:
        h = hashlib.sha256(token.encode()).hexdigest()
    else:
        if "anon_id" not in session:
            session["anon_id"] = str(uuid.uuid4())
        h = hashlib.sha256(session["anon_id"].encode()).hexdigest()
    return h[:24]


def get_thread_id(session, shared_thread=False):
    """Return thread id — shared or per-user."""
    return "shared_global_thread" if shared_thread else get_user_shortid(session)


def history_path_for(thread_id, chat_dir):
    return os.path.join(chat_dir, f"{thread_id}.json")


# === JSON thread handling (for personal chats) ===

def load_thread(thread_id, chat_dir):
    """Load personal or shared chat thread. Shared uses YAML memory now."""
    if thread_id == "shared_global_thread":
        return load_shared_thread()

    p = history_path_for(thread_id, chat_dir)
    if os.path.exists(p):
        try:
            with open(p, "r") as f:
                data = json.load(f)
                if isinstance(data, list):
                    if not data or data[0].get("role") != "system":
                        data.insert(0, {"role": "system", "content": "You are CEA. Respond concisely."})
                    return data
        except Exception:
            pass
    return [{"role": "system", "content": "You are CEA. Respond concisely."}]


def save_thread(thread_id, messages, chat_dir, keep_last=20):
    """Save chat thread (YAML for shared, JSON for personal)."""
    if thread_id == "shared_global_thread":
        return save_shared_thread(messages)

    p = history_path_for(thread_id, chat_dir)
    try:
        system = [m for m in messages if m.get("role") == "system"][:1]
        others = [m for m in messages if m.get("role") != "system"]
        truncated = system + others[-(keep_last - 1):]
        _ensure_dir(p)
        with open(p, "w") as f:
            json.dump(truncated, f, indent=2)
    except Exception as e:
        raise


# === YAML-based shared memory thread ===

def get_memory_path():
    """Return the YAML file path for shared/global memory."""
    base_dir = Path(__file__).resolve().parent.parent.parent / "storage" / "instructions"
    return base_dir / "memory.yaml"


def load_shared_thread():
    """Load the shared global thread from memory.yaml."""
    path = get_memory_path()
    data = load_yaml(path)
    if "conversation" not in data or not isinstance(data["conversation"], list):
        data["conversation"] = [{"role": "system", "content": "You are CEA. Respond concisely."}]
    return data["conversation"]


def save_shared_thread(messages):
    """Save shared/global thread back into memory.yaml."""
    path = get_memory_path()
    data = load_yaml(path)
    data["conversation"] = messages
    save_yaml(path, data)

