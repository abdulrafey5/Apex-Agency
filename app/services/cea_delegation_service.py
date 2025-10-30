# /data/inception/app/services/cea_delegation_service.py
from services.autogen_coordinator import run_autogen_task
from services.grok_service import grok_chat
from services.local_cea_client import call_local_cea
import logging
import os

def delegate_cea_task(user_message, thread_context):
    """
    Main entry point used by routes/chat.py
    """
    try:
        # Tunables
        max_ctx = int(os.getenv("CEA_MAX_CONTEXT_MESSAGES", "6"))
        use_autogen = os.getenv("CEA_USE_AUTOGEN", "true").lower() in ("1", "true", "yes")
        use_grok_for_short = os.getenv("CEA_USE_GROK_FOR_SHORT", "true").lower() in ("1", "true", "yes")
        short_len = int(os.getenv("CEA_SHORT_MAX_CHARS", "140"))

        # Reduce context for speed
        ctx = thread_context[-max_ctx:] if isinstance(thread_context, list) else []

        # Fast path: short, simple prompts → Grok (faster latency)
        if use_grok_for_short and len((user_message or "").strip()) <= short_len:
            try:
                return grok_chat([{"role": "user", "content": user_message}], None)
            except Exception:
                # fall back to local CEA
                return call_local_cea(user_message)

        if use_autogen:
            result = run_autogen_task(user_message, context=ctx)
            # If it's a ranked/numbered request and output is short, auto-continue
            completed = _maybe_continue_list(user_message, result)
            return completed
        else:
            # Direct single-shot local CEA without orchestration
            base = call_local_cea(user_message)
            return _maybe_continue_list(user_message, base)
    except Exception as e:
        logging.exception("CEA delegation failed")
        # fallback: quick local CEA answer to not break UI
        try:
            return call_local_cea(user_message)
        except Exception:
            return "Sorry — CEA failed to process the request."


def _maybe_continue_list(user_message: str, text: str) -> str:
    """If user asked for top N and model returned fewer items, request continuation and append."""
    try:
        import re
        msg = (user_message or "").lower()
        # Heuristic: look for 'top' and a number N
        m = re.search(r"top\s+(\d+)", msg)
        if not m:
            return text
        target = int(m.group(1))
        # Count numbered lines like '1.' '2.' etc.
        items = re.findall(r"^\s*(\d+)\.", text, flags=re.MULTILINE)
        nums = sorted({int(n) for n in items if n.isdigit()})
        if not nums:
            return text
        last = nums[-1]
        if last >= target:
            return text
        # Ask model to continue from last+1 to target only
        remaining_prompt = (
            f"Continue the list from {last+1} to {target}. Output ONLY the remaining items, one per line, "
            f"using the same 'number. title  short description' format. Do not repeat previous items."
        )
        continuation = call_local_cea(remaining_prompt, num_predict=300, temperature=0.2)
        # Basic sanity: if continuation starts at expected number, append with a newline
        if continuation and str(last+1) + "." in continuation:
            sep = "\n\n" if not text.endswith("\n") else "\n"
            return text + sep + continuation.strip()
        return text
    except Exception:
        return text

