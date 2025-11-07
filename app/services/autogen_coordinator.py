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
        # Truncate context to prevent prompt overflow
        context_str = str(context)[:300] if context else 'none'
        if context and len(str(context)) > 300:
            context_str += "..."
        
        cea_prompt = f"""You are CEA, a decisive executive agent.
Analyse the user's task and, if needed, delegate exactly ONE clear instruction to a Worker.

Rules:
1) Do NOT ask the user questions.
2) If information is missing, make reasonable assumptions and proceed.
3) Return either JSON with key 'delegation': {{'instruction': <one instruction>, 'deliverable': <what to return>}}
   OR return a single clear instruction string for the Worker.

User task: {user_message[:500]}
Recent context: {context_str}
"""
        import os
        first_pass = int(os.getenv("CEA_FIRST_PASS_TOKENS", os.getenv("CEA_MAX_TOKENS", "200")))
        stage_timeout = int(os.getenv("CEA_STAGE_TIMEOUT_S", "300"))
        try:
            cea_resp = call_local_cea(cea_prompt, num_predict=first_pass, timeout=stage_timeout, stream=True)
        except Exception as e:
            logging.error(f"CEA analysis stage failed: {e}")
            # Fallback: use user message directly as instruction
            cea_resp = user_message
        log_agentops("cea_response", {"cea_text": cea_resp[:200]})
        delegation = parse_delegation_from_cea(cea_resp)

        # 2. Send to worker
        worker_instruction = delegation.get("instruction") if isinstance(delegation, dict) and "instruction" in delegation else cea_resp
        log_agentops("delegation_sent", {"instruction": worker_instruction[:200]})
        # Use Grok API for worker with bounded tokens
        # Allow tuning via env to avoid truncated content
        os.environ.setdefault("GROK_MAX_TOKENS", os.environ.get("GROK_MAX_TOKENS", "300"))
        worker_resp = grok_chat([{"role": "user", "content": worker_instruction}], None)
        log_agentops("worker_response", {"worker_text": worker_resp[:200]})

        # 3. Synthesize via CEA with assumption policy and no questions
        # Truncate worker output to fit in context window (max ~1500 chars = ~375 tokens)
        worker_truncated = worker_resp[:1500] if len(worker_resp) > 1500 else worker_resp
        if len(worker_resp) > 1500:
            worker_truncated += "\n[Worker output truncated...]"
        
        synth_prompt = f"""You are CEA. Produce the final deliverable for the user.

Rules:
1) Do NOT ask questions.
2) If details are missing, state assumptions briefly and deliver a complete, ready-to-use answer.
3) Prefer structured, skimmable formatting (headings, lists, tables) as appropriate.

Worker output: {worker_truncated}
Original task: {user_message[:500]}
Context: {str(context)[:200] if context else 'none'}
"""
        try:
            # Use Grok for synthesis (faster than local CEA) - can be overridden via env
            use_grok_for_synthesis = os.getenv("CEA_USE_GROK_FOR_SYNTHESIS", "true").lower() in ("1", "true", "yes")
            
            if use_grok_for_synthesis:
                # Use Grok for faster synthesis - it's already fast and produces good results
                logging.info("Using Grok for synthesis (faster than local CEA)")
                final = grok_chat([{"role": "user", "content": synth_prompt}], None)
            else:
                # Use local CEA for synthesis (slower but potentially more consistent with CEA style)
                synthesis_tokens = int(os.getenv("CEA_MAX_TOKENS", os.getenv("CEA_FIRST_PASS_TOKENS", "600")))
                final = call_local_cea(synth_prompt, num_predict=synthesis_tokens, timeout=stage_timeout, stream=True)
            
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

