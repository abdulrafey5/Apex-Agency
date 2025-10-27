# /data/inception/app/services/autogen_coordinator.py
import logging, json, time
from services.local_cea_client import call_local_cea
from services.grok_wrapper import call_worker_api
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

def run_autogen_task(user_message, context=None, timeout_total=300):
    """
    Orchestrates: CEA analyzes -> delegate -> worker -> CEA synthesizes
    Returns final text string.
    """
    logging.info("Autogen run started")
    log_agentops("task_start", {"user_message": user_message})
    # 1. Ask CEA to analyze & delegate (use a system prompt telling it to return JSON if possible)
    cea_prompt = f"""You are CEA. Analyse and if necessary delegate the following task.
Return either a JSON with keys: 'delegation': {{'instruction':..., 'deliverable':...}}
or plain text representing the worker instruction.
Task: {user_message}
Recent context: {context or 'none'}
"""
    cea_resp = call_local_cea(cea_prompt)
    log_agentops("cea_response", {"cea_text": cea_resp[:200]})
    delegation = parse_delegation_from_cea(cea_resp)

    # 2. Send to worker
    worker_instruction = delegation.get("instruction") if isinstance(delegation, dict) and "instruction" in delegation else cea_resp
    log_agentops("delegation_sent", {"instruction": worker_instruction[:200]})
    worker_resp = call_worker_api(worker_instruction)
    log_agentops("worker_response", {"worker_text": worker_resp[:200]})

    # 3. Synthesize via CEA
    synth_prompt = f"""You are CEA. Given this worker output, create the final deliverable for the user.
Worker output: {worker_resp}
Original task: {user_message}
Context: {context or 'none'}
"""
    final = call_local_cea(synth_prompt)
    log_agentops("task_completed", {"final_len": len(final)})
    return final

