from flask import Blueprint, current_app, render_template, session, request, jsonify, redirect
from pathlib import Path
import logging
import os
import json
from services.grok_service import grok_chat
from services.thread_service import load_thread, save_thread, get_thread_id
from services.cea_delegation_service import delegate_cea_task
from services.async_tasks import start_chat_task, get_task

chat_bp = Blueprint("chat", __name__)

@chat_bp.route("/healthz")
def healthz():
    return {"status": "ok"}, 200


@chat_bp.route("/chat-ui")
def chat_ui():
    """Render chat UI — supports personal and shared threads."""
    # Skip authentication for testing - remove in production
    allow_unauth = os.getenv("ALLOW_UNAUTH_CHAT", "true").lower() in ("1", "true", "yes")
    if not allow_unauth and "id_token" not in session:
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


@chat_bp.route("/chat", methods=["GET"], strict_slashes=False)
def chat_get_redirect():
    """If a GET ever hits /chat, redirect to the UI instead of 404."""
    return redirect("/chat-ui")


@chat_bp.route("/chat", methods=["POST"], strict_slashes=False)
def chat():
    """Handles chat input, sends to CEA (with delegation logic), stores replies."""
    # Skip authentication for testing - remove in production
    allow_unauth = os.getenv("ALLOW_UNAUTH_CHAT", "true").lower() in ("1", "true", "yes")
    if not allow_unauth and "id_token" not in session:
        return jsonify({"error": "Unauthorized"}), 401

    # Parse message
    # Treat explicit AJAX requests as JSON API calls even if Flask's request.is_json is False.
    is_ajax = request.headers.get("X-Requested-With") == "XMLHttpRequest"
    payload = {}
    msg = None
    if request.is_json:
        payload = request.get_json(silent=True) or {}
        msg = payload.get("message") or payload.get("prompt")
    elif is_ajax:
        # Try to parse raw body as JSON if the request claims to be AJAX
        try:
            raw = request.get_data(as_text=True)
            if raw:
                payload = json.loads(raw)
                msg = payload.get("message") or payload.get("prompt")
        except Exception:
            payload = {}
            msg = request.form.get("message") or None
    else:
        msg = request.form.get("message") or (request.json or {}).get("prompt")

    if not msg:
        return jsonify({"error": "Missing message"}), 400

    shared = current_app.config.get("SHARED_THREAD", False)
    thread_id = get_thread_id(session, shared)
    thread = load_thread(thread_id, current_app.config.get("CHAT_DIR"))
    thread.append({"role": "user", "content": msg})

    # Get reply from CEA (with delegation logic)
    try:
        reply = delegate_cea_task(msg, thread)
        thread.append({"role": "assistant", "content": reply})
        save_thread(thread_id, thread, current_app.config.get("CHAT_DIR"))
        logging.info(f"CEA reply for {thread_id}: {str(reply)[:200]}")
    except Exception as e:
        logging.exception("CEA delegation failed")
        return jsonify({"error": f"CEA delegation failed: {e}"}), 500

    # For browser (regular form nav) redirect; for JSON/AJAX clients return JSON
    if not (request.is_json or is_ajax):
        return redirect("/chat-ui")

    return jsonify({"response": reply, "thread_length": len(thread)})


@chat_bp.route("/chat-async", methods=["POST"], strict_slashes=False)
def chat_async():
    """Kick off async processing and return task_id immediately."""
    allow_unauth = os.getenv("ALLOW_UNAUTH_CHAT", "true").lower() in ("1", "true", "yes")
    if not allow_unauth and "id_token" not in session:
        return jsonify({"error": "Unauthorized"}), 401

    is_ajax = request.headers.get("X-Requested-With") == "XMLHttpRequest"
    payload = {}
    msg = None
    if request.is_json:
        payload = request.get_json(silent=True) or {}
        msg = payload.get("message") or payload.get("prompt")
    elif is_ajax:
        try:
            raw = request.get_data(as_text=True)
            if raw:
                import json as _json
                payload = _json.loads(raw)
                msg = payload.get("message") or payload.get("prompt")
        except Exception:
            payload = {}
            msg = request.form.get("message") or None
    else:
        msg = request.form.get("message") or (request.json or {}).get("prompt")

    if not msg:
        return jsonify({"error": "Missing message"}), 400

    shared = current_app.config.get("SHARED_THREAD", False)
    thread_id = get_thread_id(session, shared)
    task_id = start_chat_task(msg, thread_id, current_app.config.get("CHAT_DIR"))
    return jsonify({"task_id": task_id, "status": "queued"})


@chat_bp.route("/chat-result/<task_id>", methods=["GET"], strict_slashes=False)
def chat_result(task_id):
    data = get_task(task_id)
    return jsonify(data)


@chat_bp.route("/debug-grok")
def debug_grok():
    """Ping Grok API for quick connectivity test."""
    try:
        resp = grok_chat([{"role": "user", "content": "Ping"}], current_app.config.get("GROK"))
        return jsonify({"status": "success", "response": resp})
    except Exception as e:
        return jsonify({"status": "failed", "error": str(e)}), 500


@chat_bp.route("/debug-delegation")
def debug_delegation():
    """Test CEA delegation system."""
    try:
        from services.grok_service import grok_chat
        from services.cea_delegation_service import analyze_and_delegate

        # Test 1: Direct Grok API call
        try:
            direct_test = grok_chat([
                {"role": "user", "content": "What is 2+2? Answer with just the number."}
            ], {})
            api_working = direct_test.strip() in ["4", "Four", "four"] or "4" in direct_test
        except Exception as e:
            direct_test = f"API Failed: {str(e)}"
            api_working = False

        # Test 2: Delegation Analysis
        test_message = "Create a comprehensive marketing campaign for our new product launch including social media posts, email newsletters, and advertising banners."
        test_task = analyze_and_delegate(test_message, [])
        delegation_info = {
            "task_status": test_task.status,
            "delegations_count": len(test_task.delegations),
            "departments": list(set(d["department"] for d in test_task.delegations)) if test_task.delegations else [],
            "agents": [d["agent_file"] for d in test_task.delegations] if test_task.delegations else [],
            "test_message": test_message
        }

        # Test 3: Simple CEA response
        from services.cea_delegation_service import delegate_cea_task
        simple_test = delegate_cea_task("What is the capital of Pakistan?", [])

        return jsonify({
            "api_status": "working" if api_working else "failed",
            "delegation_analysis": delegation_info,
            "direct_grok_test": direct_test[:200] + "..." if len(direct_test) > 200 else direct_test,
            "simple_cea_test": simple_test[:200] + "..." if len(simple_test) > 200 else simple_test,
            "tests_completed": True
        })
    except Exception as e:
        logging.exception("Debug delegation failed")
        return jsonify({"status": "failed", "error": str(e)}), 500


