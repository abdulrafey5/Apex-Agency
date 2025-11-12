from services.autogen_coordinator import run_autogen_task
from services.grok_service import grok_chat
from services.local_cea_client import call_local_cea
import logging
import os

def _call_local_cea_with_context(user_message, context, num_predict=None, stream=True, timeout=300, temperature=None):
    """Helper to call local CEA with conversation context."""
    from services.local_cea_client import call_local_cea
    return call_local_cea(user_message, stream=stream, timeout=timeout, num_predict=num_predict, temperature=temperature, context=context)


def _force_truncate_top_n(text: str, target: int) -> str:
    """ABSOLUTE FINAL TRUNCATION: Force truncate to exactly target items, no exceptions."""
    try:
        import re
        if not text or not text.strip():
            return text
        
        # Find all numbered items
        lines = text.split("\n")
        result_lines = []
        items_found = []
        
        for line in lines:
            # Check if this line starts a numbered item
            item_match = re.match(r"^\s*(\d+)\.", line)
            if item_match:
                item_num = int(item_match.group(1))
                items_found.append(item_num)
                
                if item_num > target:
                    # Found item beyond target - STOP HERE, don't include this line
                    logging.warning(f"_force_truncate_top_n: Stopping at item {item_num} (target is {target})")
                    break
                else:
                    # Item is target or less - include it
                    result_lines.append(line)
            else:
                # Not a numbered item - include it if we haven't exceeded target
                if not items_found or items_found[-1] <= target:
                    result_lines.append(line)
                else:
                    # We've already exceeded target - stop
                    break
        
        truncated = "\n".join(result_lines).rstrip()
        
        # AGGRESSIVE VERIFICATION: Count items and verify
        final_items = re.findall(r"^\s*(\d+)\.", truncated, flags=re.MULTILINE)
        final_nums = sorted({int(n) for n in final_items if n.isdigit()})
        
        if final_nums and final_nums[-1] > target:
            # Still failed - this should never happen, but force it anyway
            logging.error(f"_force_truncate_top_n: CRITICAL - Still have {final_nums[-1]} items after truncation, forcing again")
            # Find the position of item #target and cut everything after it
            target_marker = f"{target}."
            target_pos = truncated.find(target_marker)
            if target_pos >= 0:
                # Find where item #target ends (next item marker or end of text)
                next_marker = f"{target + 1}."
                next_pos = truncated.find(next_marker, target_pos)
                if next_pos >= 0:
                    truncated = truncated[:next_pos].rstrip()
                else:
                    # Item #(target+1) not found, but we know it exists
                    # Find it by looking for any number > target
                    for i, line in enumerate(lines):
                        item_match = re.match(r"^\s*(\d+)\.", line)
                        if item_match and int(item_match.group(1)) > target:
                            # Found it - truncate before this line
                            truncated = "\n".join(lines[:i]).rstrip()
                            break
        
        # Final check - if still wrong, use nuclear option
        final_check = re.findall(r"^\s*(\d+)\.", truncated, flags=re.MULTILINE)
        final_check_nums = sorted({int(n) for n in final_check if n.isdigit()})
        if final_check_nums and final_check_nums[-1] > target:
            logging.error(f"_force_truncate_top_n: NUCLEAR OPTION - Manually removing all items > {target}")
            result_lines = []
            for line in lines:
                item_match = re.match(r"^\s*(\d+)\.", line)
                if item_match:
                    if int(item_match.group(1)) > target:
                        break
                result_lines.append(line)
            truncated = "\n".join(result_lines).rstrip()
        
        logging.info(f"_force_truncate_top_n: Final result has items: {re.findall(r'^\s*(\d+)\.', truncated, flags=re.MULTILINE)}")
        return truncated
    except Exception as e:
        logging.error(f"_force_truncate_top_n error: {e}")
        return text


def delegate_cea_task(user_message, thread_context):
    """
    Main entry point used by routes/chat.py
    """
    import re
    result = None
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
                # Build conversation history for Grok (it accepts messages list)
                messages = []
                # Add previous conversation context (last few messages)
                if ctx and isinstance(ctx, list):
                    for msg in ctx[-4:]:  # Last 4 messages for context
                        if isinstance(msg, dict) and "role" in msg and "content" in msg:
                            messages.append({"role": msg["role"], "content": msg["content"]})
                # Add current user message
                messages.append({"role": "user", "content": f"{user_message}. Provide a concise, factual answer."})
                
                grok_text = grok_chat(messages, None)
                # Pass Grok output through completion logic; use local CEA for continuations
                grok_text = _maybe_continue_list(user_message, grok_text)
                grok_text = _ensure_complete(user_message, grok_text)
                return grok_text
            except Exception:
                # fall back to local CEA with context
                base = _call_local_cea_with_context(user_message, ctx)
                base = _maybe_continue_list(user_message, base)
                return _ensure_complete(user_message, base)

        if use_autogen:
            result = run_autogen_task(user_message, context=ctx)
            # Always run completion logic to ensure responses are complete
            cont_max = int(os.getenv("CEA_CONTINUE_MAX_ITERS", "5"))
            if cont_max > 0:
                # First, handle "top N" lists - this respects the exact number requested
                import re
                is_top_n_request = bool(re.search(r"top\s+(\d+)", (user_message or "").lower()))
                
                if is_top_n_request:
                    # For "top N" requests, handle truncation/continuation first
                    result = _maybe_continue_list(user_message, result)
                    # CRITICAL: After _maybe_continue_list, verify we have exactly the target number
                    target_match = re.search(r"top\s+(\d+)", (user_message or "").lower())
                    if target_match:
                        target = int(target_match.group(1))
                        items = re.findall(r"^\s*(\d+)\.", result, flags=re.MULTILINE)
                        nums = sorted({int(n) for n in items if n.isdigit()})
                        if nums:
                            last_item = nums[-1]
                            logging.info(f"delegate_cea_task: After _maybe_continue_list, 'Top {target}' list has {last_item} items")
                            
                            # If we have exactly target items and it ends properly, we're done
                            text_ends_properly = result.rstrip().endswith((".", "!", "?", ":", "\"", ")", "]", "}"))
                            if last_item == target and text_ends_properly:
                                # Perfect - exactly target items, ends properly - SKIP _ensure_complete
                                logging.info(f"delegate_cea_task: 'Top {target}' list has exactly {last_item} items and ends properly, skipping _ensure_complete")
                                # FINAL SAFETY CHECK: Verify we don't have more than target items
                                final_verify_items = re.findall(r"^\s*(\d+)\.", result, flags=re.MULTILINE)
                                final_verify_nums = sorted({int(n) for n in final_verify_items if n.isdigit()})
                                if final_verify_nums and final_verify_nums[-1] > target:
                                    logging.error(f"delegate_cea_task: CRITICAL - Found {final_verify_nums[-1]} items in final result, forcing absolute truncation")
                                    result = _force_truncate_top_n(result, target)
                                return result
                            elif last_item > target:
                                # Still have too many items - truncate again (shouldn't happen, but safety check)
                                logging.error(f"delegate_cea_task: 'Top {target}' list still has {last_item} items after _maybe_continue_list, truncating again")
                                result = _force_truncate_top_n(result, target)
                                return result
                            elif last_item < target:
                                # Still need more items - but _maybe_continue_list should have handled this
                                # Only run _ensure_complete if the last item is incomplete
                                if not text_ends_properly:
                                    # Last item incomplete - complete it but don't go beyond target
                                    logging.info(f"delegate_cea_task: 'Top {target}' list has {last_item} items but last is incomplete, completing last item only")
                                    # Use a custom completion that respects the target
                                    result = _complete_top_n_item(user_message, result, target)
                                # If it ends properly but we have fewer items, that's fine - return as-is
                                return result
                        else:
                            # No items found - this shouldn't happen, but return as-is
                            logging.warning(f"delegate_cea_task: 'Top {target}' request but no numbered items found in result")
                            return result
                else:
                    # Not a "top N" request - run both functions normally
                    result = _maybe_continue_list(user_message, result)
                    result = _ensure_complete(user_message, result, max_iters=cont_max)
            
            # ABSOLUTE FINAL CHECK: For "top N" requests, force truncation one more time before returning
            import re
            is_top_n_final = bool(re.search(r"top\s+(\d+)", (user_message or "").lower()))
            if is_top_n_final:
                target_match_final = re.search(r"top\s+(\d+)", (user_message or "").lower())
                if target_match_final:
                    target_final = int(target_match_final.group(1))
                    final_items_check = re.findall(r"^\s*(\d+)\.", result, flags=re.MULTILINE)
                    final_nums_check = sorted({int(n) for n in final_items_check if n.isdigit()})
                    if final_nums_check and final_nums_check[-1] > target_final:
                        logging.error(f"delegate_cea_task: ABSOLUTE FINAL - Found {final_nums_check[-1]} items, forcing truncation to {target_final}")
                        result = _force_truncate_top_n(result, target_final)
            
            return result
        else:
            # Direct single-shot local CEA without orchestration
            first_pass_tokens = int(os.getenv("CEA_FIRST_PASS_TOKENS", os.getenv("CEA_MAX_TOKENS", "500")))
            base = _call_local_cea_with_context(user_message, ctx, num_predict=first_pass_tokens)
            cont_max = int(os.getenv("CEA_CONTINUE_MAX_ITERS", "0"))
            if cont_max > 0:
                # 🔧 FIX: Check if this is a "top N" request BEFORE calling _ensure_complete
                import re
                is_top_n_check = bool(re.search(r"top\s+(\d+)", (user_message or "").lower()))
                
                base = _maybe_continue_list(user_message, base)
                
                if is_top_n_check:
                    # For "top N" requests, DON'T call _ensure_complete if we have correct count
                    target_check = re.search(r"top\s+(\d+)", (user_message or "").lower())
                    if target_check:
                        target = int(target_check.group(1))
                        items = re.findall(r"^\s*(\d+)\.", base, flags=re.MULTILINE)
                        nums = sorted({int(n) for n in items if n.isdigit()})
                        
                        if nums and nums[-1] == target:
                            # We have exactly the right number - DON'T call _ensure_complete
                            logging.info(f"delegate_cea_task: Skipping _ensure_complete for 'top {target}' - already have {target} items")
                            text_ends_properly = base.rstrip().endswith((".", "!", "?", ":", "\"", ")", "]", "}"))
                            if not text_ends_properly:
                                # Only complete the last item if it's incomplete
                                base = _complete_top_n_item(user_message, base, target)
                        elif nums and nums[-1] > target:
                            # Too many items - truncate
                            logging.warning(f"delegate_cea_task: 'Top {target}' has {nums[-1]} items, truncating")
                            base = _force_truncate_top_n(base, target)
                        else:
                            # Fewer items - only complete if last item is incomplete
                            text_ends_properly = base.rstrip().endswith((".", "!", "?", ":", "\"", ")", "]", "}"))
                            if not text_ends_properly and nums:
                                base = _complete_top_n_item(user_message, base, target)
                else:
                    # Not a "top N" request - run _ensure_complete normally
                    base = _ensure_complete(user_message, base, max_iters=cont_max)
            
            # ABSOLUTE FINAL CHECK for non-autogen path too
            import re
            is_top_n_final = bool(re.search(r"top\s+(\d+)", (user_message or "").lower()))
            if is_top_n_final:
                target_match_final = re.search(r"top\s+(\d+)", (user_message or "").lower())
                if target_match_final:
                    target_final = int(target_match_final.group(1))
                    final_items_check = re.findall(r"^\s*(\d+)\.", base, flags=re.MULTILINE)
                    final_nums_check = sorted({int(n) for n in final_items_check if n.isdigit()})
                    if final_nums_check and final_nums_check[-1] > target_final:
                        logging.error(f"delegate_cea_task: ABSOLUTE FINAL (non-autogen) - Found {final_nums_check[-1]} items, forcing truncation to {target_final}")
                        base = _force_truncate_top_n(base, target_final)
            
            result = base
    except Exception as e:
        logging.exception("CEA delegation failed")
        # fallback: quick local CEA answer to not break UI
        try:
            result = call_local_cea(user_message)
        except Exception:
            result = "Sorry — CEA failed to process the request."
    
    # ABSOLUTE FINAL CHECK: ALWAYS apply truncation for "top N" requests, no matter what path was taken
    if result:
        is_top_n = bool(re.search(r"top\s+(\d+)", (user_message or "").lower()))
        if is_top_n:
            target_match = re.search(r"top\s+(\d+)", (user_message or "").lower())
            if target_match:
                target = int(target_match.group(1))
                items_before = re.findall(r"^\s*(\d+)\.", result, flags=re.MULTILINE)
                nums_before = sorted({int(n) for n in items_before if n.isdigit()})
                if nums_before and nums_before[-1] > target:
                    logging.warning(f"delegate_cea_task: FINAL CHECK - Found {nums_before[-1]} items for 'top {target}', forcing truncation")
                    result = _force_truncate_top_n(result, target)
                    items_after = re.findall(r"^\s*(\d+)\.", result, flags=re.MULTILINE)
                    nums_after = sorted({int(n) for n in items_after if n.isdigit()})
                    logging.info(f"delegate_cea_task: After final truncation, result has {len(nums_after)} items: {nums_after}")
    
    return result


def _complete_top_n_item(user_message: str, text: str, target: int) -> str:
    """Complete the last item in a 'top N' list without going beyond target."""
    try:
        import re
        items = re.findall(r"^\s*(\d+)\.", text, flags=re.MULTILINE)
        nums = sorted({int(n) for n in items if n.isdigit()})
        if not nums:
            return text
        last = nums[-1]
        
        if last >= target:
            return text  # Already have enough items
        
        # Complete the last item only
        last_item_marker = f"{last}."
        last_marker_pos = text.rfind(last_item_marker)
        if last_marker_pos >= 0:
            remaining_prompt = (
                "You previously wrote the following answer.\n\n" +
                text.strip() +
                "\n\n" +
                f"Complete item {last} (it was cut off). Output ONLY the completed item {last}, using the same format. Do not add any more items. When finished, append [END]."
            )
            import os
            cont_tokens = int(os.getenv("CEA_CONTINUE_TOKENS", "600"))
            continuation = call_local_cea(remaining_prompt, num_predict=cont_tokens, temperature=0.2, stream=True)
            if continuation and continuation.strip():
                last_item_start = text.rfind(last_item_marker)
                if last_item_start >= 0:
                    text_before_last = text[:last_item_start].rstrip()
                    return text_before_last + "\n\n" + continuation.strip().replace("[END]", "").strip()
        return text
    except Exception as e:
        logging.warning(f"_complete_top_n_item error: {e}")
        return text


def _maybe_continue_list(user_message: str, text: str) -> str:
    """If user asked for top N, ensure exactly N items. Truncate if more, continue if fewer."""
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
        
        # CRITICAL: If we have MORE items than requested, TRUNCATE to exactly target
        if last > target:
            logging.warning(f"_maybe_continue_list: Found {last} items but target is {target}, truncating to {target}")
            # BULLETPROOF APPROACH: Find the exact position where item #(target+1) starts and cut there
            lines = text.split("\n")
            result_lines = []
            
            # Go through each line and stop when we see item #(target+1) or higher
            for line in lines:
                # Check if this line starts a numbered item
                item_match = re.match(r"^\s*(\d+)\.", line)
                if item_match:
                    item_num = int(item_match.group(1))
                    if item_num > target:
                        # Found item beyond target - STOP HERE, don't include this line
                        logging.info(f"_maybe_continue_list: Found item {item_num}, stopping (target is {target})")
                        break
                    else:
                        # Item is target or less - include it
                        result_lines.append(line)
                else:
                    # Not a numbered item - include it (it's part of a previous item's description)
                    result_lines.append(line)
            
            # Join and clean up
            truncated = "\n".join(result_lines).rstrip()
            
            # AGGRESSIVE VERIFICATION: Count items and force truncation if needed
            final_items = re.findall(r"^\s*(\d+)\.", truncated, flags=re.MULTILINE)
            final_nums = sorted({int(n) for n in final_items if n.isdigit()})
            
            if final_nums and final_nums[-1] > target:
                # Still have too many - this means our truncation failed, force it
                logging.error(f"_maybe_continue_list: CRITICAL - Still have {final_nums[-1]} items, forcing truncation")
                # Find the line number where item #target ends
                result_lines = []
                for line in lines:
                    item_match = re.match(r"^\s*(\d+)\.", line)
                    if item_match:
                        item_num = int(item_match.group(1))
                        if item_num > target:
                            break
                    result_lines.append(line)
                truncated = "\n".join(result_lines).rstrip()
            
            # Remove any trailing blank lines and ensure proper ending
            truncated = truncated.rstrip()
            if truncated and not truncated.endswith((".", "!", "?", ":", "\"", ")", "]", "}")):
                truncated = truncated + "."
            
            # Final verification - count again
            final_check = re.findall(r"^\s*(\d+)\.", truncated, flags=re.MULTILINE)
            final_check_nums = sorted({int(n) for n in final_check if n.isdigit()})
            if final_check_nums and final_check_nums[-1] > target:
                # Last resort: manually remove items beyond target
                logging.error(f"_maybe_continue_list: EMERGENCY - Manually removing items beyond {target}")
                lines_final = truncated.split("\n")
                result_final = []
                for line in lines_final:
                    item_match = re.match(r"^\s*(\d+)\.", line)
                    if item_match:
                        if int(item_match.group(1)) > target:
                            break
                    result_final.append(line)
                truncated = "\n".join(result_final).rstrip()
            
            logging.info(f"_maybe_continue_list: After truncation, returning text with items: {re.findall(r'^\s*(\d+)\.', truncated, flags=re.MULTILINE)}")
            return truncated
        
        # If we have exactly target items, check if the last one is complete
        if last == target:
            text_ends_properly = text.rstrip().endswith((".", "!", "?", ":", "\"", ")", "]", "}"))
            if text_ends_properly:
                # We have exactly target items and they end properly - PERFECT, return as-is
                logging.info(f"_maybe_continue_list: Have exactly {target} items and ends properly, returning as-is")
                return text
            # Last item might be incomplete - complete it but don't go beyond
            last_item_marker = f"{last}."
            last_marker_pos = text.rfind(last_item_marker)
            if last_marker_pos >= 0:
                after_marker = text[last_marker_pos + len(last_item_marker):].strip()
                if after_marker and not text_ends_properly:
                    # Complete item #target only
                    remaining_prompt = (
                        "You previously wrote the following answer.\n\n" +
                        text.strip() +
                        "\n\n" +
                        f"Complete item {target} (it was cut off). Output ONLY the completed item {target}, using the same format. Do not add any more items. When finished, append [END]."
                    )
                    import os
                    cont_tokens = int(os.getenv("CEA_CONTINUE_TOKENS", "600"))
                    continuation = call_local_cea(remaining_prompt, num_predict=cont_tokens, temperature=0.2, stream=True)
                    if continuation and continuation.strip():
                        # Replace the incomplete last item
                        last_item_start = text.rfind(last_item_marker)
                        if last_item_start >= 0:
                            text_before_last = text[:last_item_start].rstrip()
                            return text_before_last + "\n\n" + continuation.strip().replace("[END]", "").strip()
            return text
        
        # We have fewer than target items - continue to reach target
        text_ends_properly = text.rstrip().endswith((".", "!", "?", ":", "\"", ")", "]", "}"))
        last_item_incomplete = False
        
        # Check if the last numbered item's description seems incomplete
        last_item_marker = f"{last}."
        last_marker_pos = text.rfind(last_item_marker)
        if last_marker_pos >= 0:
            after_marker = text[last_marker_pos + len(last_item_marker):].strip()
            if after_marker and not text_ends_properly:
                last_item_incomplete = True
        
        # Determine starting point: if last item is incomplete, complete it first, then continue
        start_from = last if last_item_incomplete else (last + 1)
        
        # Ask model to continue from start_from to target (exactly target, no more)
        remaining_prompt = (
            "You previously wrote the following answer.\n\n" +
            text.strip() +
            "\n\n" +
            (f"Complete item {last} (it was cut off), then continue the list from {last+1} to {target} (exactly {target} items total, no more)."
             if last_item_incomplete and last < target
             else f"Continue the list from {start_from} to {target} (exactly {target} items total, no more).") +
            " Output ONLY the remaining items, using the same format (number. title, short description). " +
            "Do not repeat previous items. Stop at item {target}. When finished, append [END]."
        )
        import os
        cont_tokens = int(os.getenv("CEA_CONTINUE_TOKENS", "600"))
        continuation = call_local_cea(remaining_prompt, num_predict=cont_tokens, temperature=0.2, stream=True)
        
        if not continuation or not continuation.strip():
            return text
        
        # Remove [END] marker
        continuation = continuation.strip().replace("[END]", "").strip()
        
        # Check for duplicates: if continuation contains items that already exist in text, skip them
        existing_items = set(re.findall(r"^\s*(\d+)\.", text, flags=re.MULTILINE))
        continuation_items = re.findall(r"^\s*(\d+)\.", continuation, flags=re.MULTILINE)
        
        # Filter out items that already exist
        new_items = [item for item in continuation_items if item not in existing_items]
        if not new_items:
            # All items in continuation already exist - don't append
            logging.warning(f"_maybe_continue_list: Continuation contains only duplicate items, skipping")
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
                    combined = text_before_last + "\n\n" + continuation
                    # Verify we don't exceed target
                    final_items = re.findall(r"^\s*(\d+)\.", combined, flags=re.MULTILINE)
                    final_nums = sorted({int(n) for n in final_items if n.isdigit()})
                    if final_nums and final_nums[-1] > target:
                        # We exceeded target - truncate at target
                        logging.warning(f"_maybe_continue_list: Continuation exceeded target {target}, truncating")
                        # Find where item #target ends
                        target_marker = f"{target}."
                        target_pos = combined.find(target_marker)
                        if target_pos >= 0:
                            # Find the end of item #target (next item marker or end of text)
                            next_item_pos = combined.find(f"{target+1}.", target_pos)
                            if next_item_pos >= 0:
                                combined = combined[:next_item_pos].rstrip()
                            # Ensure it ends properly
                            if not combined.rstrip().endswith((".", "!", "?", ":", "\"", ")", "]", "}")):
                                # Add a period if needed
                                combined = combined.rstrip() + "."
                    return combined
            combined = text + sep + continuation
            # Verify we don't exceed target
            final_items = re.findall(r"^\s*(\d+)\.", combined, flags=re.MULTILINE)
            final_nums = sorted({int(n) for n in final_items if n.isdigit()})
            if final_nums and final_nums[-1] > target:
                # We exceeded target - truncate at target
                logging.warning(f"_maybe_continue_list: Continuation exceeded target {target}, truncating")
                target_marker = f"{target}."
                target_pos = combined.find(target_marker)
                if target_pos >= 0:
                    next_item_pos = combined.find(f"{target+1}.", target_pos)
                    if next_item_pos >= 0:
                        combined = combined[:next_item_pos].rstrip()
                    if not combined.rstrip().endswith((".", "!", "?", ":", "\"", ")", "]", "}")):
                        combined = combined.rstrip() + "."
            return combined
        
        return text
    except Exception as e:
        logging.warning(f"_maybe_continue_list error: {e}")
        return text


def _looks_truncated(text: str, user_message: str = None) -> bool:
    """Detect if text appears truncated. Improved detection for mid-word/sentence cuts."""
    if not text:
        return False
    
    # 🔧 NEW: Check if this is a "top N" request and we have N items
    if user_message:
        import re
        m = re.search(r"top\s+(\d+)", (user_message or "").lower())
        if m:
            target = int(m.group(1))
            items = re.findall(r"^\s*(\d+)\.", text, flags=re.MULTILINE)
            nums = sorted({int(n) for n in items if n.isdigit()})
            if nums and nums[-1] == target:
                # We have exactly the target number of items
                tail = text.rstrip()
                if tail.endswith((".", "!", "?", ":", "\"", ")", "]", "}")):
                    # Ends properly with correct count - NOT truncated
                    logging.info(f"_looks_truncated: 'Top {target}' list has exactly {target} items and ends properly - NOT truncated")
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
            
            # Check if response ends with a table but no closing statement
            # For comprehensive guides/campaigns, they usually end with a summary or conclusion
            if "|" in tail[-300:]:  # Table in last 300 chars
                # Check if there's any text after the last table (closing statement, summary, etc.)
                lines = tail.split("\n")
                last_table_line_idx = None
                for i in range(len(lines) - 1, max(0, len(lines) - 20), -1):  # Check last 20 lines
                    if "|" in lines[i]:
                        last_table_line_idx = i
                        break
                
                if last_table_line_idx is not None:
                    # Found a table - check if there's substantial content after it
                    content_after_table = "\n".join(lines[last_table_line_idx + 1:]).strip()
                    # If there's a table near the end but no closing statement, likely incomplete
                    if len(content_after_table) < 50:
                        # Check if the last line of the table is complete (has proper ending)
                        last_table_line = lines[last_table_line_idx].strip()
                        if not last_table_line.endswith("|") or last_table_line.count("|") < 2:
                            return True
                        # Table seems complete but no closing - might be OK, but for comprehensive guides, usually have a closing
                        # Only flag as incomplete if the response is very long (suggests it should have a closing)
                        if len(tail) > 3000:  # Very long response should have a closing statement
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
    if "|" in tail[-200:]:  # If there's a pipe in the last 200 chars, might be a table (increased range)
        # Check if it ends with incomplete table cell or row
        if tail.rstrip().endswith(("|", "| ", "|  ", "*", "**", "***")):
            return True
        # Check if last line looks like an incomplete table row (ends with text but no closing "|")
        lines = tail.split("\n")
        last_line = lines[-1].strip() if lines else tail.strip()
        if "|" in last_line:
            # If it's a table row, it should end with "|" - if not, it's incomplete
            if not last_line.endswith("|"):
                # Incomplete table row - missing closing pipe
                return True
            # Check if the table row has the same number of columns as the header
            # Find the table header (look for a line with "|" that's not the last line)
            header_pipe_count = None
            for line in reversed(lines[:-1]):  # Check lines before the last one
                line_stripped = line.strip()
                if "|" in line_stripped and line_stripped.startswith("|"):
                    # Found a potential header - count pipes
                    header_pipe_count = line_stripped.count("|")
                    break
            
            # Count pipes in the last row
            last_pipe_count = last_line.count("|")
            
            # If we found a header and the last row has fewer pipes, it's incomplete
            if header_pipe_count is not None and last_pipe_count < header_pipe_count:
                logging.info(f"_looks_truncated: Table row has {last_pipe_count} pipes but header has {header_pipe_count} - incomplete")
                return True
            
            # Even if it ends with "|", check if the row looks complete (has enough cells)
            # A complete table row typically has multiple "|" separators
            if last_pipe_count < 2:  # Less than 2 pipes suggests incomplete row
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
    """If output appears truncated, request continuations and append. Uses Grok for faster, more reliable continuations."""
    try:
        import os
        import re
        
        # 🔍 DEBUG: Check if this is being called for "top N" requests
        is_top_n = bool(re.search(r"top\s+(\d+)", (user_message or "").lower()))
        if is_top_n:
            target_match = re.search(r"top\s+(\d+)", (user_message or "").lower())
            if target_match:
                target = int(target_match.group(1))
                items = re.findall(r"^\s*(\d+)\.", text, flags=re.MULTILINE)
                nums = sorted({int(n) for n in items if n.isdigit()})
                logging.warning(f"⚠️ _ensure_complete called for 'top {target}' request with {len(nums)} items: {nums}")
        
        out = text or ""
        iters = 0
        cont_tokens = int(os.getenv("CEA_CONTINUE_TOKENS", "800"))
        # Use Grok for continuation (faster and more reliable than local CEA)
        use_grok_for_continuation = os.getenv("CEA_USE_GROK_FOR_CONTINUATION", "true").lower() in ("1", "true", "yes")
        
        while iters < max_iters and _looks_truncated(out, user_message):
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
            
            # Detect if we're in a table context
            is_table_context = "|" in truncated_context[-200:]
            table_instruction = ""
            if is_table_context:
                table_instruction = "CRITICAL: The previous content ends in an incomplete table row. You MUST complete that table row first (match the number of columns in the header), then complete any remaining table rows, then finish the section. "
            
            continuation_prompt = (
                f"You previously wrote the following answer (showing last portion for context):\n\n{truncated_context}\n\n"
                f"Continue the answer from where it was cut off. Do not repeat content. Keep the same format and "
                f"finish any incomplete bullets, sentences, sections, or tables. Complete the answer fully. "
                f"{table_instruction}"
                f"IMPORTANT: If the previous content ends mid-table, complete that table row first (ensure it has the same number of columns as the header), then complete any remaining table rows and sections. "
                f"Provide a complete continuation that finishes the current section and completes the entire answer. "
                f"When you are fully finished, append the token [END] at the end."
            )
            
            try:
                # Use Grok for continuation (faster and more reliable)
                if use_grok_for_continuation:
                    logging.info(f"_ensure_complete: Using Grok for continuation (iteration {iters})")
                    cont = grok_chat([{"role": "user", "content": continuation_prompt}], None)
                else:
                    # Fallback to local CEA if Grok is disabled
                    cont = call_local_cea(continuation_prompt, num_predict=cont_tokens, temperature=0.2, stream=True)
            except Exception as e:
                error_msg = str(e)
                logging.warning(f"_ensure_complete: continuation call failed at iteration {iters}: {error_msg}")
                # If Grok fails, try local CEA as fallback
                if use_grok_for_continuation:
                    try:
                        logging.info(f"_ensure_complete: Grok failed, trying local CEA as fallback")
                        cont = call_local_cea(continuation_prompt, num_predict=cont_tokens, temperature=0.2, stream=True)
                    except Exception as e2:
                        error_msg = str(e2)
                        logging.warning(f"_ensure_complete: Local CEA fallback also failed: {error_msg}")
                        # Check if it's a connection error (Ollama not running)
                        if "Connection refused" in error_msg or "Failed to reach local CEA model" in error_msg:
                            logging.error(f"_ensure_complete: Both Grok and Ollama unavailable. Cannot complete response.")
                            if _looks_truncated(out, user_message):
                                out = out + "\n\n[Note: Response may be incomplete due to service unavailability]"
                            break
                        # For other errors, try again if we have iterations left
                        if iters >= max_iters:
                            break
                        continue
                else:
                    # Local CEA failed - check if it's a connection error
                    if "Connection refused" in error_msg or "Failed to reach local CEA model" in error_msg:
                        logging.error(f"_ensure_complete: Ollama appears to be unavailable. Cannot complete response.")
                        if _looks_truncated(out, user_message):
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
            
            # IMPROVED De-duplication: Check multiple ways to detect duplicate content
            should_skip = False
            
            # 1. Check for exact duplicate sentences (if continuation is mostly duplicate sentences, skip)
            if len(out) > 200 and len(cont_clean) > 100:
                out_sentences = set(re.split(r'[.!?]\s+', out[-1500:].lower()))
                cont_sentences = re.split(r'[.!?]\s+', cont_clean.lower())
                if len(cont_sentences) > 0:
                    duplicate_sentences = sum(1 for s in cont_sentences if s.strip() and len(s.strip()) > 20 and s.strip() in out_sentences)
                    if duplicate_sentences / len(cont_sentences) > 0.6:
                        logging.warning(f"_ensure_complete: Continuation contains {duplicate_sentences}/{len(cont_sentences)} duplicate sentences, skipping")
                        should_skip = True
            
            # 2. Check for duplicate numbered items (if continuation repeats numbered items, skip)
            if not should_skip and len(cont_clean) > 50:
                existing_items = set(re.findall(r"^\s*(\d+)\.", out, flags=re.MULTILINE))
                continuation_items = re.findall(r"^\s*(\d+)\.", cont_clean, flags=re.MULTILINE)
                if continuation_items:
                    duplicate_items = sum(1 for item in continuation_items if item in existing_items)
                    if duplicate_items / len(continuation_items) > 0.5:
                        logging.warning(f"_ensure_complete: Continuation contains {duplicate_items}/{len(continuation_items)} duplicate numbered items, skipping")
                        should_skip = True
            
            # 3. Check for substantial text overlap (if >70% of continuation matches existing content, skip)
            if not should_skip and len(out) > 500 and len(cont_clean) > 100:
                last_1500 = out[-1500:].lower()
                cont_lower = cont_clean.lower()
                # Use word-level overlap
                out_words = set(last_1500.split())
                cont_words = cont_lower.split()
                if len(cont_words) > 10:
                    matching_words = sum(1 for word in cont_words if len(word) > 3 and word in out_words)  # Only count words > 3 chars
                    if matching_words / len(cont_words) > 0.7:
                        logging.warning(f"_ensure_complete: Continuation has {matching_words}/{len(cont_words)} words overlapping with existing content, skipping")
                        should_skip = True
            
            # 4. Check for exact duplicate at the end (if continuation head matches output tail exactly)
            if not should_skip and len(out) > 100 and len(cont_clean) > 50:
                out_tail = out[-100:].lower().strip()
                cont_head = cont_clean[:100].lower().strip()
                if len(cont_head) > 50 and out_tail[-50:] == cont_head[:50]:
                    logging.warning(f"_ensure_complete: Continuation head exactly matches output tail, skipping")
                    should_skip = True
            
            if should_skip:
                # Skip this continuation, but check if output is complete
                if not _looks_truncated(out, user_message):
                    logging.info(f"_ensure_complete: Output appears complete after skipping duplicate continuation")
                    break
                # Output still looks truncated but continuation is duplicate - try one more time
                if iters >= max_iters:
                    break
                continue
            
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
                if not _looks_truncated(out, user_message):
                    logging.info(f"_ensure_complete: Output appears complete with [END], stopping")
                    break
                else:
                    logging.info(f"_ensure_complete: [END] found but output still looks truncated, continuing...")
                    continue
            
            # CRITICAL: Always check if the FULL output looks truncated, regardless of how continuation ended
            # This ensures we continue even if continuation ends properly but full output is still incomplete
            if _looks_truncated(out, user_message):
                logging.info(f"_ensure_complete: Full output still looks truncated after continuation, continuing...")
                continue
            
            # If we get here, the full output doesn't look truncated
            # But also check if continuation ends properly as a secondary check
            if cont_ends_properly:
                logging.info(f"_ensure_complete: Full output appears complete and continuation ends properly, stopping")
                break
            else:
                # Continuation doesn't end properly but full output doesn't look truncated
                # This might be a false negative - continue to be safe
                logging.info(f"_ensure_complete: Full output doesn't look truncated but continuation ends oddly, continuing to be safe...")
                continue
        
        # FINAL CHECK: Before returning, verify the output is actually complete
        # If it still looks truncated after all iterations, log a warning
        if _looks_truncated(out, user_message):
            logging.warning(f"_ensure_complete: Output still appears truncated after {iters} iterations. Length: {len(out)}")
            # Don't add a note here - let it return as-is, but log the issue
        
        return out
    except Exception as e:
        logging.warning(f"_ensure_complete error: {e}")
        return text