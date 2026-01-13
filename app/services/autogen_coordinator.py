# /data/inception/app/services/autogen_coordinator.py
import logging, json, time
from services.local_cea_client import call_local_cea
from services.grok_service import grok_chat
from services.rag_service import query_semantic_memory
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
    
    # ============================================================================
    # STEP 0: Retrieve RAG context from semantic_memory (Issue 3 Fix)
    # ============================================================================
    rag_context = ""
    try:
        # Query semantic memory for relevant context
        rag_results = query_semantic_memory(
            query_text=user_message,
            top_k=5,
            match_threshold=0.6
        )
        if rag_results:
            rag_parts = []
            for result in rag_results:
                content = result.get("content", "")
                metadata = result.get("metadata", {})
                source_type = metadata.get("source_type", "unknown")
                similarity = result.get("similarity", 0.0)
                rag_parts.append(f"[Knowledge Base - {source_type}]: {content[:400]}")
            rag_context = "\n\n".join(rag_parts)
            logging.info(f"✅ Retrieved {len(rag_results)} RAG context documents from semantic_memory")
        else:
            logging.info("No RAG context found for this query")
    except Exception as e:
        logging.warning(f"RAG context retrieval failed: {e}")
        rag_context = ""
    
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

        # Include RAG context in CEA prompt
        rag_section = f"\n\nRelevant Knowledge Base Context:\n{rag_context}\n" if rag_context else ""
        
        cea_prompt = f"""You are CEA, a decisive executive agent.
Analyse the user's task and, if needed, delegate exactly ONE clear instruction to a Worker.

Rules:
1) Do NOT ask the user questions.
2) If information is missing, make reasonable assumptions and proceed.
3) Use the conversation context to understand references like "it", "that", "the waterfall", etc.
4) Use the Knowledge Base Context below to inform your analysis and delegation.
5) Return either JSON with key 'delegation': {{'instruction': <one instruction>, 'deliverable': <what to return>}}
   OR return a single clear instruction string for the Worker.

Conversation context:
{context_str}
{rag_section}
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

        # 2. Send to worker with context (Issue 1 Fix: Use EC2 instead of Grok)
        worker_instruction = delegation.get("instruction") if isinstance(delegation, dict) and "instruction" in delegation else cea_resp
        log_agentops("delegation_sent", {"instruction": worker_instruction[:200]})
        
        # Build worker prompt with context and RAG
        worker_context_str = ""
        if context and isinstance(context, list):
            context_parts = []
            for msg in context[-3:]:  # Last 3 messages for context
                if isinstance(msg, dict) and "role" in msg and "content" in msg:
                    role = msg["role"]
                    content = str(msg["content"])[:150]
                    if role == "user":
                        context_parts.append(f"Previous user: {content}")
                    elif role == "assistant":
                        context_parts.append(f"Previous assistant: {content}")
            if context_parts:
                worker_context_str = "\n".join(context_parts)
        
        if not worker_context_str:
            worker_context_str = "none"
        
        worker_rag_section = f"\n\nRelevant Knowledge Base Context:\n{rag_context}\n" if rag_context else ""
        worker_prompt = f"""You are a Worker agent executing a task delegated by CEA.

Conversation context:
{worker_context_str}
{worker_rag_section}
Task instruction: {worker_instruction}

Execute this task completely and provide a detailed response."""
        
        # Use EC2 compute (call_local_cea) instead of Grok API
        logging.info("Using EC2 compute (call_local_cea) for worker execution")
        worker_tokens = int(os.getenv("CEA_MAX_TOKENS", os.getenv("CEA_FIRST_PASS_TOKENS", "500")))
        try:
            worker_resp = call_local_cea(worker_prompt, num_predict=worker_tokens, timeout=stage_timeout, stream=True, context=context)
        except Exception as e:
            logging.error(f"Worker execution failed on EC2: {e}, falling back to Grok")
            # Fallback to Grok only if EC2 fails
            worker_messages = []
            if context and isinstance(context, list):
                for msg in context[-3:]:
                    if isinstance(msg, dict) and "role" in msg and "content" in msg:
                        worker_messages.append({"role": msg["role"], "content": msg["content"]})
            worker_messages.append({"role": "user", "content": worker_instruction})
            worker_resp = grok_chat(worker_messages, None)
        log_agentops("worker_response", {"worker_text": worker_resp[:200]})

        # 3. Synthesize via CEA with assumption policy and no questions (Issue 1 Fix: Use EC2 instead of Grok)
        # For local CEA with 1024 token context: prompt ~200 tokens, context ~100 tokens, leaving ~724 tokens
        # But we need room for synthesis output, so truncate worker output more aggressively
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

        # Include RAG context in synthesis prompt
        synth_rag_section = f"\n\nRelevant Knowledge Base Context:\n{rag_context}\n" if rag_context else ""
        
        synth_prompt = f"""You are CEA. Produce the final deliverable for the user.

Rules:
1) Do NOT ask questions.
2) If details are missing, state assumptions briefly and deliver a complete, ready-to-use answer.
3) Use the conversation context to understand references like "it", "that", "the waterfall", etc.
4) Use the Knowledge Base Context below to inform your synthesis.
5) Prefer structured, skimmable formatting (headings, lists, tables) as appropriate.

Conversation context:
{synth_context_str}
{synth_rag_section}
Worker output: {worker_truncated}
Original task: {user_message[:500]}
"""
        try:
            # Issue 1 Fix: Default to EC2 compute (can be overridden via env for testing)
            use_grok_for_synthesis = os.getenv("CEA_USE_GROK_FOR_SYNTHESIS", "false").lower() in ("1", "true", "yes")

            if use_grok_for_synthesis:
                # Only use Grok if explicitly enabled (for testing/debugging)
                logging.info("Using Grok for synthesis (override enabled)")
                # Include context in synthesis messages
                synth_messages = []
                if context and isinstance(context, list):
                    for msg in context[-3:]:  # Last 3 messages
                        if isinstance(msg, dict) and "role" in msg and "content" in msg:
                            synth_messages.append({"role": msg["role"], "content": msg["content"]})
                synth_messages.append({"role": "user", "content": synth_prompt})
                final = grok_chat(synth_messages, None)
            else:
                # Default: Use EC2 compute (local CEA) for synthesis
                logging.info("✅ Using EC2 compute (LOCAL CEA model gpt-oss:20b) for synthesis")
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

