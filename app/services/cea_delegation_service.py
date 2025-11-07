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
        # Count numbered lines like '1.' '2.' etc. - also check for incomplete last item
        items = re.findall(r"^\s*(\d+)\.", text, flags=re.MULTILINE)
        nums = sorted({int(n) for n in items if n.isdigit()})
        if not nums:
            return text
        last = nums[-1]
        
        # Check if the last item appears incomplete (ends mid-sentence without proper punctuation)
        # This handles cases where item 9 is cut off and item 10 is missing
        # Simple heuristic: if text doesn't end with proper punctuation, it's likely truncated
        text_ends_properly = text.rstrip().endswith((".", "!", "?", ":", "\"", ")", "]", "}"))
        last_item_incomplete = False
        
        # Also check if the last numbered item's description seems incomplete
        # Find the last occurrence of "last." and check what comes after it
        last_item_marker = f"{last}."
        last_marker_pos = text.rfind(last_item_marker)
        if last_marker_pos >= 0:
            # Get text after the last item marker
            after_marker = text[last_marker_pos + len(last_item_marker):].strip()
            # If there's text after the marker but it doesn't end with punctuation, it's incomplete
            if after_marker and not text_ends_properly:
                last_item_incomplete = True
        
        # If we have fewer items than requested OR the last item is incomplete, trigger continuation
        if last >= target and not last_item_incomplete:
            return text
        
        # Determine starting point: if last item is incomplete, complete it first, then continue
        start_from = last if last_item_incomplete else (last + 1)
        
        # Ask model to continue from start_from to target
        remaining_prompt = (
            "You previously wrote the following answer.\n\n" +
            text.strip() +
            "\n\n" +
            (f"Complete item {last} (it was cut off), then continue the list from {last+1} to {target}."
             if last_item_incomplete and last < target
             else f"Continue the list from {start_from} to {target}.") +
            " Output ONLY the remaining items, using the same format (number. title, short description). " +
            "Do not repeat previous items. When finished, append [END]."
        )
        import os
        cont_tokens = int(os.getenv("CEA_CONTINUE_TOKENS", "600"))
        continuation = call_local_cea(remaining_prompt, num_predict=cont_tokens, temperature=0.2, stream=True)
        
        if not continuation or not continuation.strip():
            return text
        
        # If continuation starts at expected number or completes the last item, append it
        continuation_starts_correctly = (
            (str(start_from) + "." in continuation) or 
            (last_item_incomplete and (str(last) + "." in continuation or continuation.strip().startswith(str(last))))
        )
        
        if continuation_starts_correctly:
            sep = "\n\n" if not text.rstrip().endswith(("\n", "\n\n")) else "\n"
            # If last item was incomplete, we might need to replace it rather than append
            if last_item_incomplete and str(last) + "." in continuation:
                # Find where the last item starts and replace from there
                last_item_start = text.rfind(str(last) + ".")
                if last_item_start >= 0:
                    # Keep everything before the incomplete last item, then append continuation
                    text_before_last = text[:last_item_start].rstrip()
                    return text_before_last + "\n\n" + continuation.strip()
            return text + sep + continuation.strip()
        
        return text
    except Exception as e:
        logging.warning(f"_maybe_continue_list error: {e}")
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

