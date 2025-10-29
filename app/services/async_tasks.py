import threading
import uuid
import logging
from typing import Dict, Any
from services.thread_service import load_thread, save_thread
from services.cea_delegation_service import delegate_cea_task


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
        thread = load_thread(thread_id, chat_dir)
        thread.append({"role": "user", "content": message})
        reply = delegate_cea_task(message, thread)
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


