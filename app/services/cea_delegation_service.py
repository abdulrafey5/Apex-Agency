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

        # Fast path: short, simple prompts → Grok (faster latency, concise responses)
        # Check if prompt is short AND looks like a simple factual question (not a complex request)
        user_msg_clean = (user_message or "").strip()
        is_simple_question = (
            len(user_msg_clean) <= short_len and
            # Simple questions: "What is X?", "Population of X", "Capital of X", etc.
            (not any(word in user_msg_clean.lower() for word in ["help", "create", "launch", "plan", "campaign", "strategy", "guide", "how to", "step"]))
        )
        
        if use_grok_for_short and is_simple_question:
            try:
                # For simple questions, use Grok directly with a concise prompt
                grok_text = grok_chat([{"role": "user", "content": f"{user_message}. Provide a concise, factual answer."}], None)
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
            # Always run completion logic to ensure responses are complete
            cont_max = int(os.getenv("CEA_CONTINUE_MAX_ITERS", "3"))
            if cont_max > 0:
                result = _maybe_continue_list(user_message, result)
                result = _ensure_complete(user_message, result, max_iters=cont_max)
            # Final check: if result still looks truncated, log warning
            if _looks_truncated(result):
                logging.warning(f"delegate_cea_task: Result still appears truncated after completion logic. Length: {len(result)}")
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
    """Detect if text appears truncated. Improved detection for mid-word/sentence cuts."""
    if not text:
        return False
    tail = text.rstrip()
    # If [END] marker is present, consider it complete
    if "[END]" in tail:
        return False
    
    # Check if it ends with proper sentence-ending punctuation
    if tail.endswith((".", "!", "?")):
        # Additional check: if it ends with punctuation but the last word is suspiciously short,
        # it might still be cut off (e.g., "conte." where "conte" is incomplete)
        words = tail.split()
        if words:
            last_word = words[-1].rstrip(".,!?;:)\"]}")
            if len(last_word) < 4:  # Very short word before punctuation might indicate truncation
                return True
        # If it ends with proper punctuation, check if it looks like a complete thought
        # For longer responses (like guides), check if the last sentence is complete
        if len(tail) > 500:  # Longer responses should have more structure
            # Check if last sentence ends properly (not mid-bullet or mid-list)
            last_sentence = tail.split(".")[-1] if "." in tail else tail
            # If last "sentence" is very short or looks incomplete, might be truncated
            if len(last_sentence.strip()) < 20:
                return True
            # Check if it ends mid-section (e.g., "### 7.4 Daily Optimization Cadence" followed by incomplete content)
            # Look for section headers (###, ##, #) near the end - if there's a header but no content after, it's incomplete
            last_lines = tail.split("\n")[-10:] if "\n" in tail else [tail]  # Check last 10 lines for better detection
            for line in reversed(last_lines):
                line_stripped = line.strip()
                # If we find a section header (starts with #) near the end, check if there's substantial content after
                if line_stripped.startswith(("#", "##", "###", "####")):
                    # Found a header - check if there's enough content after it
                    header_pos = tail.rfind(line_stripped)
                    content_after = tail[header_pos + len(line_stripped):].strip()
                    # If there's a header but less than 100 chars of content after, likely incomplete
                    # Also check if the header suggests multiple items (e.g., "Cadence", "Timeline", "Steps") but only one item exists
                    header_lower = line_stripped.lower()
                    suggests_multiple = any(word in header_lower for word in ["cadence", "timeline", "steps", "phases", "schedule", "checklist", "items", "tasks"])
                    if suggests_multiple:
                        # Count bullet points or numbered items after the header
                        bullets_after = content_after.count("-") + content_after.count("*") + content_after.count("•")
                        numbered_items = len([l for l in content_after.split("\n") if l.strip() and (l.strip()[0].isdigit() or l.strip().startswith(("-", "*", "•")))])
                        # If header suggests multiple items but we only see 1-2 items, likely incomplete
                        if numbered_items <= 2 and bullets_after <= 2:
                            return True
                    # If there's a header but less than 100 chars of content after, likely incomplete
                    if len(content_after) < 100:
                        return True
                    break
        return False
    
    # If it ends with mid-sentence punctuation (comma, colon, semicolon, etc.), it's likely truncated
    if tail.endswith((",", ":", ";", ")", "]", "}", "\"", "+", "-", "|")):
        return True
    
    # Check for incomplete table cells or markdown structures
    # If it ends with "|" or "+" or "-" (common in tables), it's likely truncated
    if tail.rstrip().endswith(("|", "+", "-")) and not tail.rstrip().endswith(("---", "===")):
        return True
    
    # If it doesn't end with any punctuation, it's likely truncated
    # Check if last word is suspiciously short (mid-word cut)
    words = tail.split()
    if words:
        last_word = words[-1]
        # If last word is very short (< 4 chars) and doesn't look like a complete word, likely truncated
        # Also check for symbols like "+", "-", "|" which indicate incomplete content
        if len(last_word) < 4 or last_word in ("+", "-", "|"):
            return True
    
    # Check if it ends mid-table (common pattern: ends with "|" or incomplete cell)
    if "|" in tail[-100:]:  # If there's a pipe in the last 100 chars, might be a table
        # Check if it ends with incomplete table cell or row
        if tail.rstrip().endswith(("|", "| ", "|  ", "*", "**", "***")):
            return True
        # Check if last line looks like an incomplete table row (ends with text but no closing "|")
        last_line = tail.split("\n")[-1].strip() if "\n" in tail else tail.strip()
        if "|" in last_line:
            # If it's a table row, it should end with "|" - if not, it's incomplete
            if not last_line.endswith("|"):
                # Incomplete table row - missing closing pipe
                return True
            # Even if it ends with "|", check if the row looks complete (has enough cells)
            # A complete table row typically has multiple "|" separators
            pipe_count = last_line.count("|")
            if pipe_count < 2:  # Less than 2 pipes suggests incomplete row
                return True
        # Check if it ends with markdown formatting that suggests incomplete content
        if last_line.endswith(("*", "**", "***", "`", "```")):
            return True
    
    # Check for incomplete markdown structures (bold, italic, code blocks)
    # Also check if it ends with incomplete markdown like "**Data Quality" (starts with ** but incomplete)
    if tail.rstrip().endswith(("*", "**", "***", "`", "```", "|")):
        return True
    
    # Get last line for markdown checks (avoid duplicate)
    last_line_for_md = tail.split("\n")[-1].strip() if "\n" in tail else tail.strip()
    
    # Check if last line starts with markdown but is incomplete (e.g., "**Data Quality" without closing)
    if last_line_for_md.startswith(("**", "***", "`", "```")) and not last_line_for_md.endswith(("**", "***", "`", "```")):
        # Started markdown formatting but didn't close it - likely truncated
        return True
    # Check if it ends with text that looks like it's starting a markdown section (e.g., "**Data Quality")
    if last_line_for_md.startswith("**") and len(last_line_for_md.split()) <= 3:
        # Looks like a markdown header that was cut off
        return True
    
    # Default: if no proper ending punctuation, consider truncated
    return True


def _ensure_complete(user_message: str, text: str, max_iters: int = 3) -> str:
    """If output appears truncated, request continuations and append. Uses smart truncation to preserve token budget."""
    try:
        import os
        out = text or ""
        iters = 0
        cont_tokens = int(os.getenv("CEA_CONTINUE_TOKENS", "600"))
        
        while iters < max_iters and _looks_truncated(out):
            iters += 1
            logging.info(f"_ensure_complete: iteration {iters}, text length: {len(out)}")
            
            # Smart truncation: Keep only the last ~1000 chars of previous text to preserve token budget for continuation
            # This ensures we have room for the continuation prompt + actual continuation content
            # ~1000 chars ≈ ~250 tokens, leaving ~750 tokens for continuation in a 1024 token context
            # More aggressive truncation to ensure continuation has enough room
            max_context_chars = 1000
            if len(out) > max_context_chars:
                # Keep the beginning (first 150 chars for context) and the end (last portion)
                # This gives better context while preserving more tokens for continuation
                context_start = out[:150] + "\n[... earlier content ...]\n"
                remaining_chars = max_context_chars - len(context_start)
                context_end = out[-remaining_chars:] if remaining_chars > 0 else out[-800:]
                truncated_context = context_start + context_end
                logging.info(f"_ensure_complete: truncated context from {len(out)} to {len(truncated_context)} chars")
            else:
                truncated_context = out
            
            continuation_prompt = (
                f"You previously wrote the following answer (showing last portion for context):\n\n{truncated_context}\n\n"
                f"Continue the answer from where it was cut off. Do not repeat content. Keep the same format and "
                f"finish any incomplete bullets, sentences, sections, or tables. Complete the answer fully. "
                f"IMPORTANT: If the previous content ends mid-table, complete that table row and any remaining table rows. "
                f"Provide a complete continuation that finishes the current section and completes the entire answer. "
                f"When you are fully finished, append the token [END] at the end."
            )
            
            try:
                cont = call_local_cea(continuation_prompt, num_predict=cont_tokens, temperature=0.2, stream=True)
            except Exception as e:
                error_msg = str(e)
                logging.warning(f"_ensure_complete: continuation call failed at iteration {iters}: {error_msg}")
                # Check if it's a connection error (Ollama not running)
                if "Connection refused" in error_msg or "Failed to reach local CEA model" in error_msg:
                    logging.error(f"_ensure_complete: Ollama appears to be unavailable. Cannot complete response.")
                    # Return what we have with a note that it may be incomplete
                    if _looks_truncated(out):
                        out = out + "\n\n[Note: Response may be incomplete due to Ollama service unavailability]"
                    break
                # For other errors, try again if we have iterations left
                if iters >= max_iters:
                    break
                continue
                
            if not cont or not cont.strip():
                logging.warning(f"_ensure_complete: empty continuation at iteration {iters}")
                # If we have more iterations, try again
                if iters >= max_iters:
                    break
                continue
            
            # Remove [END] marker if present
            cont_clean = cont.strip().replace("[END]", "").strip()
            
            # Better de-duplication: check if continuation is substantially different from what we already have
            # Only check if continuation is long enough to avoid false positives
            if len(cont_clean) > 100:
                # Compare last 100 chars of out with first 100 chars of cont to avoid appending duplicates
                # Use a more lenient check - only reject if there's very high overlap
                if len(out) > 100:
                    out_tail = out[-100:].lower().strip()
                    cont_head = cont_clean[:100].lower().strip()
                    # Only reject if the continuation head is almost identical to the output tail
                    # This prevents false positives when continuation naturally continues from where it left off
                    if len(cont_head) > 50 and out_tail[-50:] == cont_head[:50]:
                        logging.warning(f"_ensure_complete: continuation appears to be duplicate (high overlap), stopping")
                        break
            
            # Append continuation
            sep = "\n\n" if not out.rstrip().endswith(("\n", "\n\n")) else "\n"
            out = out + sep + cont_clean
            
            # Check if continuation ended with [END] or proper sentence-ending punctuation (likely complete)
            # Don't stop if it ends with comma, colon, etc. - those indicate it's still incomplete
            cont_ends_properly = cont_clean.rstrip().endswith((".", "!", "?"))
            
            # If continuation is very short (< 100 chars), it's likely incomplete or cut off
            if len(cont_clean.strip()) < 100:
                logging.info(f"_ensure_complete: continuation is very short ({len(cont_clean)} chars), likely incomplete, continuing...")
                # Don't break - continue to next iteration
                continue
            
            # Check if [END] marker is present
            if "[END]" in cont:
                logging.info(f"_ensure_complete: [END] marker found, checking if output is complete...")
                # Even with [END], verify the output doesn't look truncated
                if not _looks_truncated(out):
                    logging.info(f"_ensure_complete: Output appears complete with [END], stopping")
                    break
                else:
                    logging.info(f"_ensure_complete: [END] found but output still looks truncated, continuing...")
                    continue
            
            # Check if continuation ends properly
            if cont_ends_properly:
                # CRITICAL: Check if the FULL output now ends properly and doesn't look truncated
                if out.rstrip().endswith((".", "!", "?")) and not _looks_truncated(out):
                    logging.info(f"_ensure_complete: Full output appears complete, stopping")
                    break
                else:
                    # Continuation ends properly but full output still looks truncated - continue
                    logging.info(f"_ensure_complete: Continuation ends properly but full output still looks truncated, continuing...")
                    continue
            else:
                # Continuation itself might be truncated (ends with comma, colon, etc.) - continue
                logging.info(f"_ensure_complete: continuation ends with mid-sentence punctuation ({cont_clean[-10:]}), continuing...")
                continue
        
        # FINAL CHECK: Before returning, verify the output is actually complete
        # If it still looks truncated after all iterations, log a warning
        if _looks_truncated(out):
            logging.warning(f"_ensure_complete: Output still appears truncated after {iters} iterations. Length: {len(out)}")
            # Don't add a note here - let it return as-is, but log the issue
        
        return out
    except Exception as e:
        logging.warning(f"_ensure_complete error: {e}")
        return text

