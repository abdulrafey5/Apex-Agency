import hashlib
import uuid
import base64
import json
from services.db_service import get_db_service


def get_user_shortid(session):
    """
    Generate a stable short ID for the user or anonymous session.
    For authenticated users: Extract stable 'sub' claim from JWT id_token.
    For anonymous users: Use persistent anon_id from session.
    """
    token = session.get("id_token")
    if token:
        try:
            # Extract stable user ID from JWT token (sub claim)
            # JWT format: header.payload.signature
            parts = token.split(".")
            if len(parts) >= 2:
                # Decode payload (add padding if needed)
                payload = parts[1]
                # Add padding if needed for base64 decoding
                padding = len(payload) % 4
                if padding:
                    payload += "=" * (4 - padding)
                decoded = base64.urlsafe_b64decode(payload)
                claims = json.loads(decoded)
                # Use 'sub' (subject) claim as stable user identifier
                user_sub = claims.get("sub")
                if user_sub:
                    # Hash the stable sub claim for thread_id
                    import hashlib as _hashlib
                    h = _hashlib.sha256(user_sub.encode()).hexdigest()
                    return h[:24]
        except Exception as e:
            import logging
            logging.warning(f"Failed to extract user ID from token: {e}, falling back to token hash")
            # Fallback: hash the entire token (less stable but works)
            import hashlib as _hashlib
            h = _hashlib.sha256(token.encode()).hexdigest()
            return h[:24]
    
    # Anonymous user: use persistent anon_id
    if "anon_id" not in session:
        session["anon_id"] = str(uuid.uuid4())
        # Persist anon_id in session permanently
        session.permanent = True
    h = hashlib.sha256(session["anon_id"].encode()).hexdigest()
    return h[:24]


def get_thread_id(session, shared_thread=False):
    """Return thread id — shared or per-user."""
    return "shared_global_thread" if shared_thread else get_user_shortid(session)


def load_thread(thread_id, chat_dir=None, limit: int = 200):
    """Load thread messages from Postgres. Falls back to a default system prompt."""
    import logging
    try:
        db = get_db_service()
        if not db.pool:
            logging.warning(f"Database pool not initialized - using default system prompt. Check database connection.")
            return [{"role": "system", "content": "You are CEA. Respond concisely."}]
        
        rows = db.get_thread_messages(thread_id, limit=limit, offset=0)
        if rows:
            messages = [{"role": r.get("role"), "content": r.get("message_text"), "metadata": r.get("metadata")} for r in rows]
            logging.info(f"✅ Loaded {len(messages)} messages for thread {thread_id}")
            return messages
        else:
            # No messages found - this is OK for new threads
            logging.info(f"No existing messages found for thread {thread_id} - starting new thread")
            return [{"role": "system", "content": "You are CEA. Respond concisely."}]
    except RuntimeError as e:
        logging.warning(f"Database error loading thread {thread_id}: {e}. Using default system prompt.")
    except Exception as e:
        logging.warning(f"Error loading thread {thread_id}: {e}. Using default system prompt.")
    return [{"role": "system", "content": "You are CEA. Respond concisely."}]


def save_thread(thread_id, messages, chat_dir=None, keep_last=200):
    """Persist thread messages to Postgres, truncating to the last keep_last entries."""
    import logging
    try:
        db = get_db_service()
        if not db.pool:
            logging.error(f"Database pool not initialized - cannot save thread messages. Check database connection.")
            return
        
        system = [m for m in messages if m.get("role") == "system"][:1]
        others = [m for m in messages if m.get("role") != "system"]
        truncated = system + others[-(keep_last - 1):]
        
        saved_count = db.replace_thread_messages(thread_id, truncated)
        logging.info(f"✅ Saved {saved_count} messages for thread {thread_id}")
    except RuntimeError as e:
        logging.error(f"Database error saving thread {thread_id}: {e}")
    except Exception as e:
        logging.exception(f"Unexpected error saving thread {thread_id}: {e}")

