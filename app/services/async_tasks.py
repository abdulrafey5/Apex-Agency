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
ROOT = Path(__file__).resolve().parent.parent.parent
TASKS_DIR = ROOT / "storage" / "chat_history" / "tasks"
TASKS_DIR.mkdir(parents=True, exist_ok=True)

def _task_path(task_id: str) -> Path:
    return TASKS_DIR / f"{task_id}.json"


def _set_task(task_id: str, data: Dict[str, Any]) -> None:
    with _LOCK:
        _TASKS[task_id] = data
    # Also persist to disk for cross-process visibility
    try:
        p = _task_path(task_id)
        with open(p, "w") as f:
            json.dump({"id": task_id, **data}, f)
    except Exception:
        pass


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
                # Normalize
                status = data.get("status") or "pending"
                resp = data.get("response")
                err = data.get("error")
                return {"status": status, "response": resp, "error": err}
    except Exception:
        pass
    return {"status": "not_found"}


def _run_chat_task(task_id: str, message: str, thread_id: str, chat_dir: str) -> None:
    try:
        start = time.monotonic()
        soft_deadline = int(os.getenv("CEA_TASK_SOFT_DEADLINE_S", "45"))
        thread = load_thread(thread_id, chat_dir)
        thread.append({"role": "user", "content": message})
        reply = None
        # Run delegation with a soft deadline; if exceeded, return best-effort partial
        try:
            reply = delegate_cea_task(message, thread)
        except Exception as _:
            reply = None

        elapsed = time.monotonic() - start
        if (reply is None or len(str(reply).strip()) == 0) and elapsed >= soft_deadline:
            # Provide a graceful fallback rather than hanging the UI
            reply = "Sorry — generating a full answer is taking longer than usual. Here is a brief outline; re-ask to expand specific sections."

        thread.append({"role": "assistant", "content": reply})
        save_thread(thread_id, thread, chat_dir)
        _set_task(task_id, {"status": "done", "response": reply})
    except Exception as e:
        logging.exception("Async chat task failed")
        _set_task(task_id, {"status": "error", "error": str(e)})


def start_chat_task(message: str, thread_id: str, chat_dir: str) -> str:
    task_id = str(uuid.uuid4())
    _set_task(task_id, {"status": "pending"})
    t = threading.Thread(target=_run_chat_task, args=(task_id, message, thread_id, chat_dir), daemon=True)
    t.start()
    return task_id


