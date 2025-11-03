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
                grok_text = grok_chat([{"role": "user", "content": user_message}], None)
                # Pass Grok output through completion logic; use local CEA for continuations
                grok_text = _maybe_continue_list(user_message, grok_text)
                grok_text = _ensure_complete(user_message, grok_text)
                return grok_text
            except Exception:
                # fall back to local CEA
                base = call_local_cea(user_message)
                base = _maybe_continue_list(user_message, base)
                return _ensure_complete(user_message, base)

        if use_autogen:
            result = run_autogen_task(user_message, context=ctx)
            # Optional minimal completion based on env
            cont_max = int(os.getenv("CEA_CONTINUE_MAX_ITERS", "0"))
            if cont_max > 0:
                result = _maybe_continue_list(user_message, result)
                result = _ensure_complete(user_message, result, max_iters=cont_max)
            return result
        else:
            # Direct single-shot local CEA without orchestration
            first_pass_tokens = int(os.getenv("CEA_FIRST_PASS_TOKENS", os.getenv("CEA_MAX_TOKENS", "500")))
            base = call_local_cea(user_message, num_predict=first_pass_tokens, stream=True)
            cont_max = int(os.getenv("CEA_CONTINUE_MAX_ITERS", "0"))
            if cont_max > 0:
                base = _maybe_continue_list(user_message, base)
                base = _ensure_complete(user_message, base, max_iters=cont_max)
            return base
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
            "You previously wrote the following answer.\n\n" +
            text.strip() +
            "\n\nContinue the list from " + str(last+1) + " to " + str(target) + ". "
            "Output ONLY the remaining items, one per line, using the same 'number. title  short description' format. "
            "Do not repeat previous items."
        )
        import os
        cont_tokens = int(os.getenv("CEA_CONTINUE_TOKENS", "400"))
        continuation = call_local_cea(remaining_prompt, num_predict=cont_tokens, temperature=0.2, stream=True)
        # Basic sanity: if continuation starts at expected number, append with a newline
        if continuation and str(last+1) + "." in continuation:
            sep = "\n\n" if not text.endswith("\n") else "\n"
            return text + sep + continuation.strip()
        return text
    except Exception:
        return text


def _looks_truncated(text: str) -> bool:
    if not text:
        return False
    tail = text.rstrip()
    # If it ends mid-sentence/word or with a dangling list bullet/number, consider truncated
    if "[END]" in tail:
        return False
    if not tail.endswith((".", "!", "?")):
        return True
    # Very short responses to seemingly broad prompts
    return False


def _ensure_complete(user_message: str, text: str, max_iters: int = 3) -> str:
    """If output appears truncated, request short continuations and append."""
    try:
        out = text or ""
        iters = 0
        while iters < max_iters and _looks_truncated(out):
            iters += 1
            continuation_prompt = (
                "You previously wrote the following answer.\n\n" + out.strip() +
                "\n\nContinue the answer until it is complete. Do not repeat content. Keep the same format and "
                "finish any incomplete bullets or sentences. When you are fully finished, append the token [END] at the end."
            )
            import os
            cont_tokens = int(os.getenv("CEA_CONTINUE_TOKENS", "400"))
            cont = call_local_cea(continuation_prompt, num_predict=cont_tokens, temperature=0.2, stream=True)
            if not cont:
                break
            # Simple de-duplication heuristic: avoid appending if mostly repeated
            if cont.strip() and cont.strip() not in out:
                sep = "\n\n" if not out.endswith("\n") else "\n"
                out = out + sep + cont.strip()
            else:
                break
        return out
    except Exception:
        return text

