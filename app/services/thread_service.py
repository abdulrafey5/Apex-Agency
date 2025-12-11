import hashlib
import uuid
from services.db_service import get_db_service


def get_user_shortid(session):
    """Generate a short unique hash for the user or anonymous session."""
    token = session.get("id_token")
    if token:
        import hashlib as _hashlib
        h = _hashlib.sha256(token.encode()).hexdigest()
    else:
        if "anon_id" not in session:
            session["anon_id"] = str(uuid.uuid4())
        h = hashlib.sha256(session["anon_id"].encode()).hexdigest()
    return h[:24]


def get_thread_id(session, shared_thread=False):
    """Return thread id — shared or per-user."""
    return "shared_global_thread" if shared_thread else get_user_shortid(session)


def load_thread(thread_id, chat_dir=None, limit: int = 200):
    """Load thread messages from Postgres. Falls back to a default system prompt."""
    try:
        db = get_db_service()
        rows = db.get_thread_messages(thread_id, limit=limit, offset=0)
        if rows:
            return [{"role": r.get("role"), "content": r.get("message_text"), "metadata": r.get("metadata")} for r in rows]
    except Exception:
        pass
    return [{"role": "system", "content": "You are CEA. Respond concisely."}]


def save_thread(thread_id, messages, chat_dir=None, keep_last=200):
    """Persist thread messages to Postgres, truncating to the last keep_last entries."""
    db = get_db_service()
    system = [m for m in messages if m.get("role") == "system"][:1]
    others = [m for m in messages if m.get("role") != "system"]
    truncated = system + others[-(keep_last - 1):]
    db.replace_thread_messages(thread_id, truncated)

