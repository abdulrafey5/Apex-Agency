# /data/inception/app/services/autogen_coordinator.py
import logging, json, time
from services.local_cea_client import call_local_cea
from services.grok_service import grok_chat
from config.agentops_config import init_agentops

# optional: agentops instrumentation
try:
    import agentops
    AGENTOPS = True
except Exception:
    AGENTOPS = False

def log_agentops(event_type, metadata):
    if not AGENTOPS:
        return
    try:
        agentops.log_event(agent="autogen", event_type=event_type, metadata=metadata)
    except Exception:
        pass

def parse_delegation_from_cea(text):
    """
    Simple heuristic: expect the CEA to return a JSON-like delegation.
    If your CEA uses explicit structured delegation produce JSON; otherwise
    we will craft a subtask prompt for the worker.
    """
    # Try to parse JSON snippet if present
    try:
        # if model returns JSON, load it
        j = json.loads(text)
        return j
    except Exception:
        # fallback: craft a worker instruction
        return {"instruction": text}

def run_autogen_task(user_message, context=None, timeout_total=120, max_turns=3):
    """
    Orchestrates: CEA analyzes -> delegate -> worker -> CEA synthesizes
    Returns final text string.
    """
    logging.info("Autogen run started")
    log_agentops("task_start", {"user_message": user_message})
    turn_count = 0
    while turn_count < max_turns:
        turn_count += 1
        # 1. Ask CEA to analyze & delegate with assumption-driven policy (no questions back to user)
        # Format context properly for the prompt
        context_str = ""
        if context and isinstance(context, list):
            context_parts = []
            for msg in context[-4:]:  # Last 4 messages
                if isinstance(msg, dict) and "role" in msg and "content" in msg:
                    role = msg["role"]
                    content = str(msg["content"])[:150]  # Limit each message
                    if role == "user":
                        context_parts.append(f"Previous user: {content}")
                    elif role == "assistant":
                        context_parts.append(f"Previous assistant: {content}")
            if context_parts:
                context_str = "\n".join(context_parts)
        
        if not context_str:
            context_str = "none"
        
        cea_prompt = f"""You are CEA, a decisive executive agent.
Analyse the user's task and, if needed, delegate exactly ONE clear instruction to a Worker.

Rules:
1) Do NOT ask the user questions.
2) If information is missing, make reasonable assumptions and proceed.
3) Use the conversation context to understand references like "it", "that", "the waterfall", etc.
4) Return either JSON with key 'delegation': {{'instruction': <one instruction>, 'deliverable': <what to return>}}
   OR return a single clear instruction string for the Worker.

Conversation context:
{context_str}

User task: {user_message[:500]}
"""
        import os
        first_pass = int(os.getenv("CEA_FIRST_PASS_TOKENS", os.getenv("CEA_MAX_TOKENS", "200")))
        stage_timeout = int(os.getenv("CEA_STAGE_TIMEOUT_S", "300"))
        try:
            cea_resp = call_local_cea(cea_prompt, num_predict=first_pass, timeout=stage_timeout, stream=True, context=context)
        except Exception as e:
            logging.error(f"CEA analysis stage failed: {e}")
            # Fallback: use user message directly as instruction
            cea_resp = user_message
        log_agentops("cea_response", {"cea_text": cea_resp[:200]})
        delegation = parse_delegation_from_cea(cea_resp)

        # 2. Send to worker with context
        worker_instruction = delegation.get("instruction") if isinstance(delegation, dict) and "instruction" in delegation else cea_resp
        log_agentops("delegation_sent", {"instruction": worker_instruction[:200]})
        # Use Grok API for worker with bounded tokens
        # Include conversation context so worker understands references
        worker_messages = []
        if context and isinstance(context, list):
            for msg in context[-3:]:  # Last 3 messages for context
                if isinstance(msg, dict) and "role" in msg and "content" in msg:
                    worker_messages.append({"role": msg["role"], "content": msg["content"]})
        worker_messages.append({"role": "user", "content": worker_instruction})
        # Allow tuning via env to avoid truncated content
        os.environ.setdefault("GROK_MAX_TOKENS", os.environ.get("GROK_MAX_TOKENS", "300"))
        worker_resp = grok_chat(worker_messages, None)
        log_agentops("worker_response", {"worker_text": worker_resp[:200]})

        # 3. Synthesize via CEA with assumption policy and no questions
        # For local CEA with 1024 token context: prompt ~200 tokens, context ~100 tokens, leaving ~724 tokens
        # But we need room for synthesis output, so truncate worker output more aggressively
        use_grok_for_synthesis = os.getenv("CEA_USE_GROK_FOR_SYNTHESIS", "true").lower() in ("1", "true", "yes")
        if use_grok_for_synthesis:
            # Grok has larger context - can use more worker output
            worker_truncated = worker_resp[:1500] if len(worker_resp) > 1500 else worker_resp
        else:
            # Local CEA: Truncate more aggressively to leave room for synthesis output
            # ~1000 chars ≈ ~250 tokens for worker output, leaving ~474 tokens for synthesis
            worker_truncated = worker_resp[:1000] if len(worker_resp) > 1000 else worker_resp
        if len(worker_resp) > len(worker_truncated):
            worker_truncated += "\n[Worker output truncated...]"
        
        # Include context in synthesis so it can understand references
        synth_context_str = ""
        if context and isinstance(context, list):
            context_parts = []
            for msg in context[-3:]:  # Last 3 messages
                if isinstance(msg, dict) and "role" in msg and "content" in msg:
                    role = msg["role"]
                    content = str(msg["content"])[:150]
                    if role == "user":
                        context_parts.append(f"Previous user: {content}")
                    elif role == "assistant":
                        context_parts.append(f"Previous assistant: {content}")
            if context_parts:
                synth_context_str = "\n".join(context_parts)
        
        if not synth_context_str:
            synth_context_str = "none"
        
        synth_prompt = f"""You are CEA. Produce the final deliverable for the user.

Rules:
1) Do NOT ask questions.
2) If details are missing, state assumptions briefly and deliver a complete, ready-to-use answer.
3) Use the conversation context to understand references like "it", "that", "the waterfall", etc.
4) Prefer structured, skimmable formatting (headings, lists, tables) as appropriate.

Conversation context:
{synth_context_str}

Worker output: {worker_truncated}
Original task: {user_message[:500]}
"""
        try:
            # Use Grok for synthesis (faster than local CEA) - can be overridden via env
            use_grok_for_synthesis = os.getenv("CEA_USE_GROK_FOR_SYNTHESIS", "true").lower() in ("1", "true", "yes")
            
            if use_grok_for_synthesis:
                # Use Grok for faster synthesis - it's already fast and produces good results
                logging.info("Using Grok for synthesis (faster than local CEA)")
                # Include context in synthesis messages
                synth_messages = []
                if context and isinstance(context, list):
                    for msg in context[-3:]:  # Last 3 messages
                        if isinstance(msg, dict) and "role" in msg and "content" in msg:
                            synth_messages.append({"role": msg["role"], "content": msg["content"]})
                synth_messages.append({"role": "user", "content": synth_prompt})
                final = grok_chat(synth_messages, None)
            else:
                # Use local CEA for synthesis (slower but potentially more consistent with CEA style)
                logging.info("Using LOCAL CEA model (gpt-oss:20b) for synthesis")
                synthesis_tokens = int(os.getenv("CEA_MAX_TOKENS", os.getenv("CEA_FIRST_PASS_TOKENS", "600")))
                # For local CEA with 1024 token context, cap synthesis tokens to fit
                # Input: ~350 tokens (prompt + worker + context), leaving ~674 tokens for output
                # But be conservative - cap at 500 to ensure we don't hit context limit
                synthesis_tokens = min(synthesis_tokens, 500)
                logging.info(f"Synthesis using {synthesis_tokens} tokens (capped for 1024 token context window)")
                final = call_local_cea(synth_prompt, num_predict=synthesis_tokens, timeout=stage_timeout, stream=True, context=context)
            
            if not final or len(final.strip()) == 0:
                # If synthesis returned empty, return worker output
                final = worker_resp[:2000] if worker_resp else "Sorry, I couldn't generate a complete response. Please try again."
        except Exception as e:
            logging.error(f"Synthesis stage failed: {e}")
            # Fallback: return worker output to avoid empty result
            final = worker_resp[:2000] if worker_resp else f"Error during synthesis: {str(e)}"
        log_agentops("task_completed", {"final_len": len(final)})
        return final
    # If max turns reached
    logging.warning("Max turns reached, returning CEA response")
    return cea_resp

