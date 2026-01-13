# Stage 1 Completion Fixes

## Issues Identified

### ❌ Issue 1: CEA Using Grok Instead of EC2
**Problem**: Autogen coordinator uses Grok for worker and synthesis, not local CEA on EC2.

**Current Code** (`app/services/autogen_coordinator.py`):
- Line 85: ✅ CEA analysis uses `call_local_cea()` (EC2) - CORRECT
- Line 106: ❌ Worker uses `grok_chat()` - WRONG, should use CEA
- Line 169: ❌ Synthesis uses `grok_chat()` - WRONG, should use CEA

**Fix**: Replace Grok calls with `call_local_cea()` for worker and synthesis.

---

### ❌ Issue 2: Autogen Not Pulling Context from Storage
**Problem**: Autogen coordinator only uses conversation thread context, doesn't query `semantic_memory` for RAG context.

**Current Code** (`app/services/autogen_coordinator.py`):
- Lines 49-64: Only formats conversation context from thread
- No call to `query_semantic_memory()` or `rag_service.query_semantic_memory()`

**Fix**: Add RAG context retrieval before building prompts.

---

### ✅ Issue 3: Persistent Memory (Should Be Working)
**Status**: `thread_service.py` uses DB-backed storage via `db_service.get_thread_messages()` and `db_service.replace_thread_messages()`.

**Verification Needed**: Confirm messages are actually persisting in `messages` table.

---

## Fixes Required

### Fix 1: Replace Grok with CEA in Autogen Coordinator

**File**: `app/services/autogen_coordinator.py`

**Changes**:

1. **Worker Step (Line 106)**: Replace Grok with CEA
```python
# OLD (Line 106):
worker_resp = grok_chat(worker_messages, None)

# NEW:
# Use local CEA for worker execution
worker_prompt = worker_instruction
if context and isinstance(context, list):
    # Add conversation context to worker prompt
    context_parts = []
    for msg in context[-3:]:
        if isinstance(msg, dict) and "role" in msg and "content" in msg:
            context_parts.append(f"{msg['role']}: {msg['content'][:200]}")
    if context_parts:
        worker_prompt = "\n".join(context_parts) + "\n\n" + worker_instruction

worker_tokens = int(os.getenv("CEA_WORKER_TOKENS", os.getenv("CEA_MAX_TOKENS", "400")))
worker_resp = call_local_cea(worker_prompt, num_predict=worker_tokens, timeout=stage_timeout, stream=True, context=context)
```

2. **Synthesis Step (Line 169)**: Replace Grok with CEA
```python
# OLD (Lines 157-169):
use_grok_for_synthesis = os.getenv("CEA_USE_GROK_FOR_SYNTHESIS", "true").lower() in ("1", "true", "yes")
if use_grok_for_synthesis:
    # ... Grok code ...
    final = grok_chat(synth_messages, None)
else:
    # ... CEA code ...

# NEW (Always use CEA):
logging.info("Using LOCAL CEA model (gpt-oss:20b) for synthesis")
synthesis_tokens = int(os.getenv("CEA_MAX_TOKENS", os.getenv("CEA_FIRST_PASS_TOKENS", "600")))
synthesis_tokens = min(synthesis_tokens, 500)  # Cap for 1024 token context
logging.info(f"Synthesis using {synthesis_tokens} tokens (capped for 1024 token context window)")
final = call_local_cea(synth_prompt, num_predict=synthesis_tokens, timeout=stage_timeout, stream=True, context=context)
```

---

### Fix 2: Add RAG Context Retrieval to Autogen

**File**: `app/services/autogen_coordinator.py`

**Add at top**:
```python
from services.rag_service import query_semantic_memory
```

**Modify `run_autogen_task()` function** - Add RAG context retrieval:

```python
def run_autogen_task(user_message, context=None, timeout_total=120, max_turns=3):
    """
    Orchestrates: CEA analyzes -> delegate -> worker -> CEA synthesizes
    Returns final text string.
    """
    logging.info("Autogen run started")
    log_agentops("task_start", {"user_message": user_message})
    
    # ============================================================================
    # NEW: Retrieve RAG context from semantic_memory
    # ============================================================================
    rag_context = ""
    try:
        # Query semantic memory for relevant context
        rag_results = query_semantic_memory(
            query_text=user_message,
            top_k=3,
            match_threshold=0.6
        )
        if rag_results:
            rag_parts = []
            for result in rag_results:
                content = result.get("content", "")
                metadata = result.get("metadata", {})
                source_type = metadata.get("source_type", "unknown")
                rag_parts.append(f"[Context from {source_type}]: {content[:300]}")
            rag_context = "\n\n".join(rag_parts)
            logging.info(f"Retrieved {len(rag_results)} RAG context documents")
    except Exception as e:
        logging.warning(f"RAG context retrieval failed: {e}")
        rag_context = ""
    
    turn_count = 0
    while turn_count < max_turns:
        turn_count += 1
        
        # Format conversation context
        context_str = ""
        if context and isinstance(context, list):
            context_parts = []
            for msg in context[-4:]:
                if isinstance(msg, dict) and "role" in msg and "content" in msg:
                    role = msg["role"]
                    content = str(msg["content"])[:150]
                    if role == "user":
                        context_parts.append(f"Previous user: {content}")
                    elif role == "assistant":
                        context_parts.append(f"Previous assistant: {content}")
            if context_parts:
                context_str = "\n".join(context_parts)

        if not context_str:
            context_str = "none"

        # ============================================================================
        # NEW: Include RAG context in CEA prompt
        # ============================================================================
        rag_section = f"\n\nRelevant Context from Knowledge Base:\n{rag_context}\n" if rag_context else ""
        
        cea_prompt = f"""You are CEA, a decisive executive agent.
Analyse the user's task and, if needed, delegate exactly ONE clear instruction to a Worker.

Rules:
1) Do NOT ask the user questions.
2) If information is missing, make reasonable assumptions and proceed.
3) Use the conversation context to understand references like "it", "that", "the waterfall", etc.
4) Use the knowledge base context below to inform your analysis.
5) Return either JSON with key 'delegation': {{'instruction': <one instruction>, 'deliverable': <what to return>}}
   OR return a single clear instruction string for the Worker.

Conversation context:
{context_str}
{rag_section}
User task: {user_message[:500]}
"""
        # ... rest of function ...
```

**Also add RAG context to synthesis prompt** (around line 141):
```python
synth_prompt = f"""You are CEA. Produce the final deliverable for the user.

Rules:
1) Do NOT ask questions.
2) If details are missing, state assumptions briefly and deliver a complete, ready-to-use answer.
3) Use the conversation context to understand references like "it", "that", "the waterfall", etc.
4) Use the knowledge base context to ensure accuracy and completeness.
5) Prefer structured, skimmable formatting (headings, lists, tables) as appropriate.

Conversation context:
{synth_context_str}
{rag_section}
Worker output: {worker_truncated}
Original task: {user_message[:500]}
"""
```

---

### Fix 3: Verify Persistent Memory

**File**: `app/services/thread_service.py` (Already correct, but verify)

**Check**: Ensure `db_service.get_thread_messages()` and `db_service.replace_thread_messages()` are working.

**Test Query**:
```sql
SELECT thread_id, role, message_text, created_at 
FROM messages 
ORDER BY created_at DESC 
LIMIT 10;
```

---

### Fix 4: Update Environment Variables

**Default Behavior**: Ensure CEA uses EC2 by default.

**Environment Variables to Set** (or ensure defaults):
```bash
# Disable Grok for synthesis (use CEA instead)
CEA_USE_GROK_FOR_SYNTHESIS=false

# Disable Grok for short questions (use CEA instead)
CEA_USE_GROK_FOR_SHORT=false

# Disable Grok for continuation (use CEA instead)
CEA_USE_GROK_FOR_CONTINUATION=false

# Disable chunked generation using Grok (or update to use CEA)
CEA_USE_CHUNKED_GENERATION=false  # Or update chunked_generation_service.py to use CEA
```

---

## Summary of Changes

1. ✅ **Replace Grok Worker with CEA** - Use `call_local_cea()` instead of `grok_chat()`
2. ✅ **Replace Grok Synthesis with CEA** - Use `call_local_cea()` instead of `grok_chat()`
3. ✅ **Add RAG Context to Autogen** - Query `semantic_memory` and include in prompts
4. ✅ **Verify Persistent Memory** - Confirm DB-backed chat history works
5. ✅ **Update Defaults** - Ensure CEA (EC2) is used by default, not Grok

---

## Testing Checklist

After fixes:

- [ ] CEA analysis uses EC2 (Ollama) - ✅ Already working
- [ ] Worker execution uses EC2 (Ollama) - ❌ Needs fix
- [ ] Synthesis uses EC2 (Ollama) - ❌ Needs fix
- [ ] Autogen prompts include RAG context - ❌ Needs fix
- [ ] Chat messages persist in DB - ✅ Should work, verify
- [ ] Context from `semantic_memory` appears in responses - ❌ Needs fix

---

## Files to Modify

1. `app/services/autogen_coordinator.py` - Replace Grok with CEA, add RAG
2. `app/services/cea_delegation_service.py` - Review for Grok usage (optional)
3. `app/services/chunked_generation_service.py` - Review for Grok usage (optional)
4. Environment variables - Set defaults to use CEA

---

## Implementation Order

1. **Fix 1**: Replace Grok with CEA in autogen coordinator (worker + synthesis)
2. **Fix 2**: Add RAG context retrieval to autogen prompts
3. **Fix 3**: Verify persistent memory works
4. **Fix 4**: Test end-to-end: User message → CEA (EC2) → RAG context → Response → DB storage



