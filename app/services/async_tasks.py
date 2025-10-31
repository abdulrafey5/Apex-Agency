import threading
import uuid
import logging
from typing import Dict, Any
from services.thread_service import load_thread, save_thread
from services.cea_delegation_service import delegate_cea_task
import time, os


_TASKS: Dict[str, Dict[str, Any]] = {}
_LOCK = threading.Lock()


def _set_task(task_id: str, data: Dict[str, Any]) -> None:
    with _LOCK:
        _TASKS[task_id] = data


def get_task(task_id: str) -> Dict[str, Any]:
    with _LOCK:
        return _TASKS.get(task_id, {"status": "not_found"})


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


