from flask import Blueprint, current_app, render_template, session, request, jsonify, redirect
from pathlib import Path
import logging
from services.grok_service import grok_chat
from services.thread_service import load_thread, save_thread, get_thread_id

chat_bp = Blueprint("chat", __name__)

@chat_bp.route("/healthz")
def healthz():
    return {"status": "ok"}, 200


@chat_bp.route("/chat-ui")
def chat_ui():
    """Render chat UI — supports personal and shared threads."""
    if "id_token" not in session:
        return redirect("/login")

    shared = current_app.config.get("SHARED_THREAD", False)
    thread_id = get_thread_id(session, shared)
    thread = load_thread(thread_id, current_app.config.get("CHAT_DIR"))
    messages = [m for m in thread if m.get("role") != "system"]
    note = "Shared thread" if shared else "Personal thread"

    # Confirm template path
    template_path = current_app.template_folder
    if not template_path or not (Path(template_path) / "chat.html").exists():
        return f"Template not found at: {template_path}/chat.html", 404

    return render_template("chat.html", messages=messages, note=note)


@chat_bp.route("/chat", methods=["POST"])
def chat():
    """Handles chat input, sends to Grok API, stores replies in YAML (shared) or JSON (user)."""
    if "id_token" not in session:
        return jsonify({"error": "Unauthorized"}), 401

    # Parse message
    if request.is_json:
        payload = request.get_json(silent=True) or {}
        msg = payload.get("message") or payload.get("prompt")
    else:
        msg = request.form.get("message") or (request.json or {}).get("prompt")

    if not msg:
        return jsonify({"error": "Missing message"}), 400

    shared = current_app.config.get("SHARED_THREAD", False)
    thread_id = get_thread_id(session, shared)
    thread = load_thread(thread_id, current_app.config.get("CHAT_DIR"))
    thread.append({"role": "user", "content": msg})

    # Get reply from Grok
    try:
        reply = grok_chat(thread, current_app.config.get("GROK"))
        thread.append({"role": "assistant", "content": reply})
        save_thread(thread_id, thread, current_app.config.get("CHAT_DIR"))
        logging.info(f"Grok reply for {thread_id}: {str(reply)[:200]}")
    except Exception as e:
        logging.exception("Grok API failed")
        return jsonify({"error": f"Grok/API failed: {e}"}), 500

    # For browser or JSON client
    if not request.is_json:
        return redirect("/chat-ui")

    return jsonify({"response": reply, "thread_length": len(thread)})


@chat_bp.route("/debug-grok")
def debug_grok():
    """Ping Grok API for quick connectivity test."""
    try:
        resp = grok_chat([{"role": "user", "content": "Ping"}], current_app.config.get("GROK"))
        return jsonify({"status": "success", "response": resp})
    except Exception as e:
        return jsonify({"status": "failed", "error": str(e)}), 500

