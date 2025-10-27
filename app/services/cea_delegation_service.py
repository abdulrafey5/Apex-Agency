# /data/inception/app/services/cea_delegation_service.py
from services.autogen_coordinator import run_autogen_task
import logging

def delegate_cea_task(user_message, thread_context):
    """
    Main entry point used by routes/chat.py
    """
    try:
        # context can be reduced for token budget
        ctx = thread_context[-10:] if isinstance(thread_context, list) else []
        result = run_autogen_task(user_message, context=ctx)
        return result
    except Exception as e:
        logging.exception("CEA delegation failed")
        # fallback: quick local CEA answer to not break UI
        from services.local_cea_client import call_local_cea
        try:
            return call_local_cea(user_message)
        except Exception:
            return "Sorry — CEA failed to process the request."

