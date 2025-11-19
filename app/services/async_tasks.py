import threading
import uuid
import logging
from typing import Dict, Any
from services.thread_service import load_thread, save_thread
from services.cea_delegation_service import delegate_cea_task
import time, os, json
from pathlib import Path


_TASKS: Dict[str, Dict[str, Any]] = {}
_LOCK = threading.Lock()

# Persist tasks so multiple workers/processes can see the same state
# Use absolute path to match main.py structure
ROOT = Path(__file__).resolve().parent.parent.parent
TASKS_DIR = ROOT / "storage" / "chat_history" / "tasks"
TASKS_DIR.mkdir(parents=True, exist_ok=True)
logging.info(f"Tasks directory: {TASKS_DIR} (exists: {TASKS_DIR.exists()})")

def _task_path(task_id: str) -> Path:
    return TASKS_DIR / f"{task_id}.json"


def _set_task(task_id: str, data: Dict[str, Any]) -> None:
    with _LOCK:
        _TASKS[task_id] = data
    # Also persist to disk for cross-process visibility
    try:
        p = _task_path(task_id)
        with open(p, "w") as f:
            json.dump({"id": task_id, **data}, f, indent=2)
        logging.debug(f"Task {task_id} persisted to {p}")
    except Exception as e:
        logging.error(f"Failed to persist task {task_id}: {e}")


def get_task(task_id: str) -> Dict[str, Any]:
    with _LOCK:
        in_mem = _TASKS.get(task_id)
    if in_mem:
        return in_mem
    # Try disk
    try:
        p = _task_path(task_id)
        if p.exists():
            with open(p, "r") as f:
                data = json.load(f)
                # Return the full payload that was persisted (minus duplicate id)
                status = data.get("status") or "pending"
                response = data.get("response")
                error = data.get("error")
                task_type = data.get("type")
                progress_log = data.get("progress_log")
                agent_insights = data.get("agent_insights")
                duration_minutes = data.get("duration_minutes")
                completed_agents = data.get("completed_agents")
                return {
                    "status": status,
                    "response": response,
                    "error": error,
                    "type": task_type,
                    "progress_log": progress_log,
                    "agent_insights": agent_insights,
                    "duration_minutes": duration_minutes,
                    "completed_agents": completed_agents
                }
    except Exception as e:
        logging.error(f"Failed to read task {task_id} from disk: {e}")
    return {"status": "not_found"}


def _run_chat_task(task_id: str, message: str, thread_id: str, chat_dir: str) -> None:
    try:
        _set_task(task_id, {"status": "processing", "response": None, "error": None})
        start = time.monotonic()
        soft_deadline = int(os.getenv("CEA_TASK_SOFT_DEADLINE_S", "600"))
        thread = load_thread(thread_id, chat_dir)
        thread.append({"role": "user", "content": message})
        reply = None
        # Run delegation with a soft deadline; if exceeded, return best-effort partial
        try:
            reply = delegate_cea_task(message, thread)
        except Exception as e:
            logging.exception(f"CEA delegation failed for task {task_id}")
            reply = None

        elapsed = time.monotonic() - start
        if soft_deadline > 0 and elapsed >= soft_deadline:
            # Provide a graceful fallback if deadline exceeded
            if reply is None or len(str(reply).strip()) == 0:
                reply = "Sorry — generating a full answer is taking longer than usual. Please try again with a more specific question."
            else:
                # Partial response, add note
                reply = reply + "\n\n[Response may be incomplete due to time constraints]"

        # If still empty, return an error so UI doesn't show a blank message
        if reply is None or len(str(reply).strip()) == 0:
            _set_task(task_id, {"status": "error", "error": "Generation timed out. Please try again.", "response": None})
            return

        thread.append({"role": "assistant", "content": reply})
        save_thread(thread_id, thread, chat_dir)
        _set_task(task_id, {"status": "done", "response": reply, "error": None})
    except Exception as e:
        logging.exception(f"Async chat task {task_id} failed")
        _set_task(task_id, {"status": "error", "error": str(e), "response": None})


def start_chat_task(message: str, thread_id: str, chat_dir: str) -> str:
    task_id = str(uuid.uuid4())
    _set_task(task_id, {"status": "pending"})
    t = threading.Thread(target=_run_chat_task, args=(task_id, message, thread_id, chat_dir), daemon=True)
    t.start()
    return task_id


def _run_incubator_task(task_id: str, business_idea: str) -> None:
    """Run incubator session in background thread."""
    try:
        _set_task(task_id, {"status": "processing", "response": None, "error": None, "type": "incubator"})
        from services.incubator_orchestrator import run_incubator_session
        session_id = task_id  # Use task_id as session_id
        result = run_incubator_session(business_idea, session_id)
        _set_task(task_id, {
            "status": result.get("status", "error"),
            "response": result.get("business_plan"),
            "error": result.get("error"),
            "type": "incubator",
            "agent_insights": result.get("agent_insights"),
            "progress_log": result.get("progress_log"),
            "duration_minutes": result.get("duration_minutes"),
            "completed_agents": result.get("completed_agents")
        })
    except Exception as e:
        logging.exception(f"Incubator task {task_id} failed")
        _set_task(task_id, {"status": "error", "error": str(e), "response": None, "type": "incubator"})


def start_incubator_task(business_idea: str) -> str:
    """Start incubator session asynchronously."""
    task_id = str(uuid.uuid4())
    _set_task(task_id, {"status": "pending", "type": "incubator"})
    t = threading.Thread(target=_run_incubator_task, args=(task_id, business_idea), daemon=True)
    t.start()
    return task_id


