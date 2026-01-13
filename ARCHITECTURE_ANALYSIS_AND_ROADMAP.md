# Architecture Analysis & Implementation Roadmap

## Current Architecture Deep Dive

### ✅ What Exists (Stage 0-1 Complete)

#### 1. **Core Agents**
- **CEA (Chief Executive Agent)**: 20B parameter model running on AWS EC2 GPU
  - Location: `app/services/local_cea_client.py`
  - Handles: Task analysis, delegation, synthesis
- **Grok Worker**: External API agent
  - Location: `app/services/grok_service.py`
  - Handles: Task execution, content generation

#### 2. **Autogen Coordinator** (Current Simple Flow)
- **File**: `app/services/autogen_coordinator.py`
- **Current Flow**: `CEA analyzes → delegates to Grok → CEA synthesizes`
- **Limitation**: Only 2 agents (CEA + Grok), no multi-level delegation

#### 3. **Database Schema** (PostgreSQL + pgvector)
- ✅ `messages` table - Chat history (DB-backed via `thread_service`)
- ✅ `semantic_memory` table - RAG knowledge base (agent library, SOPs)
- ✅ `async_tasks` table - Task tracking
- ✅ `agent_messages` table - Agent-to-agent communication (exists but not used yet)
- ✅ `agent_configs` table - Agent profiles

#### 4. **Current Request Flow**
```
User → /chat → delegate_cea_task() 
  → [Chunked Generation OR Autogen OR Direct CEA]
  → Response stored in DB via thread_service
```

#### 5. **RAG & Context**
- ✅ `rag_service.py` - Queries semantic_memory for context
- ✅ `seed_kb.py` - Populates agent library and SOPs
- ✅ Context retrieval works for agent info and SOPs

---

## Gap Analysis: Stage 0-4 Requirements

### ✅ Stage 0: Two-way Communication (COMPLETE)
- ✅ User can message CEA
- ✅ CEA responds
- ✅ Storage read/write works (DB-backed via `thread_service`)

### ✅ Stage 1: Context Storage (COMPLETE)
- ✅ CEA can reference context from `semantic_memory`
- ✅ All messages saved to persistent threads in DB
- ✅ RAG service retrieves relevant context

### ❌ Stage 2: Asynchronous Inter-Agent Communication (NOT IMPLEMENTED)
**Required Flow:**
```
CEA → DM (Department Manager) → Multiple Agents → Results back to DM → CEA → User
```

**Current State:**
- ❌ No DM layer exists
- ❌ No multi-agent orchestration (only CEA → Grok)
- ❌ No async message passing between agents
- ❌ `agent_messages` table exists but unused

**What's Needed:**
1. DM layer (e.g., Maria for Marketing)
2. Agent layer (Sofie, Adria, Colby, Coco, etc.)
3. Async message queue/threading system
4. Agent-to-agent communication protocol
5. Results aggregation (Agent → DM → CEA)

### ❌ Stage 3: Self-Review / Feedback Loop (NOT IMPLEMENTED)
**Required:**
- DMs and CEA can critique agent work
- Feedback loop with max iterations
- Scoring system for feedback importance
- Minimum score thresholds

**Current State:**
- ❌ No review/feedback mechanism
- ❌ No scoring system

### ❌ Stage 4: Autonomy (NOT IMPLEMENTED)
**Required:**
- CEA/DMs create tasks without user input
- Recurring triggers (time-based, frequency-based)
- Example: "Create Sleep blog post every day at 9am"

**Current State:**
- ❌ No autonomous task creation
- ❌ No scheduler for recurring tasks
- ❌ No self-initiated workflows

---

## Implementation Roadmap: Marketing Department First

### Phase 1: Extend Autogen for Multi-Agent (Stage 2 Foundation)

#### 1.1 Create Agent Profile System
**File**: `app/services/marketing_agents.py` (new)

```python
from dataclasses import dataclass
from enum import Enum

class MarketingAgent(Enum):
    MARIA = "maria"  # DM - Director of Marketing
    SOFIE = "sofie"  # Social Media Specialist
    ADRIA = "adria"  # Advertising Specialist
    COLBY = "colby"  # Copywriting Specialist
    COCO = "coco"    # Content Creation Specialist
    VIENNA = "vienna"  # Video Production Specialist
    NEOMI = "neomi"  # Newsletter Specialist
    INAYA = "inaya"  # Influencer Relations Specialist

@dataclass
class AgentProfile:
    name: str
    role: str
    department: str
    expertise: list
    tools: list
    communication_style: str
```

**Purpose**: Define agent identities, roles, and capabilities

#### 1.2 Extend Autogen Coordinator for Multi-Level Delegation
**File**: `app/services/autogen_coordinator.py` (extend)

**New Function**: `run_multi_agent_task()`

```python
def run_multi_agent_task(
    user_message: str,
    context=None,
    department: str = "marketing",
    timeout_total: int = 600,
    max_turns: int = 5
) -> Dict[str, Any]:
    """
    Extended Autogen flow:
    1. CEA analyzes task
    2. CEA delegates to DM (e.g., Maria)
    3. DM breaks down into agent tasks
    4. Agents execute in parallel/sequence
    5. Agents send results to DM
    6. DM aggregates and sends to CEA
    7. CEA synthesizes final response
    """
```

**Flow:**
```
CEA (analyze) 
  → DM Maria (breakdown)
    → Agent Sofie (social media)
    → Agent Colby (copywriting)
    → Agent Coco (content)
  → DM Maria (aggregate)
  → CEA (synthesize)
  → User
```

#### 1.3 Agent Communication Protocol
**File**: `app/services/agent_communication.py` (new)

**Functions:**
- `send_agent_message()` - Store agent-to-agent messages in `agent_messages` table
- `get_agent_thread()` - Retrieve conversation thread for agent
- `wait_for_agent_response()` - Async wait for agent completion
- `aggregate_agent_results()` - Combine multiple agent outputs

**Database Integration:**
- Use `agent_messages` table for all inter-agent communication
- Thread ID format: `task_{task_id}_agent_{agent_id}`
- Store delegation instructions, results, feedback

#### 1.4 Agent Execution Service
**File**: `app/services/agent_executor.py` (new)

**Functions:**
- `execute_agent_task()` - Run agent with specific role/prompt
- `get_agent_context()` - Retrieve agent profile + RAG context
- `format_agent_response()` - Structure agent output

**Agent Prompt Template:**
```python
def build_agent_prompt(agent_profile: AgentProfile, task: str, context: str) -> str:
    return f"""You are {agent_profile.name}, {agent_profile.role} in the {agent_profile.department} department.

Your expertise: {', '.join(agent_profile.expertise)}

Task: {task}

Context from previous work:
{context}

Execute this task following your role and expertise. Return your deliverable clearly marked.
"""
```

---

### Phase 2: Implement Stage 2 (Async Inter-Agent Communication)

#### 2.1 DM Layer Implementation
**File**: `app/services/dm_service.py` (new)

**DM Responsibilities:**
1. Receive task from CEA
2. Break down into agent subtasks
3. Delegate to appropriate agents
4. Aggregate results
5. Send back to CEA

**Example: Maria (Marketing DM)**
```python
def maria_delegate_task(task_description: str) -> List[Dict]:
    """
    Maria breaks down: "Create blog post + X post + Facebook ad"
    Into:
    - Colby: Write blog post
    - Sofie: Create X post
    - Adria: Create Facebook ad
    """
```

#### 2.2 Async Task Execution
**File**: `app/services/async_agent_executor.py` (new)

**Use Python `threading` or `asyncio` for parallel agent execution:**

```python
import concurrent.futures

def execute_agents_parallel(agent_tasks: List[Dict]) -> Dict[str, str]:
    """
    Execute multiple agents in parallel.
    Returns: {agent_id: result}
    """
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        futures = {
            executor.submit(execute_agent_task, task): task['agent_id']
            for task in agent_tasks
        }
        results = {}
        for future in concurrent.futures.as_completed(futures):
            agent_id = futures[future]
            results[agent_id] = future.result()
    return results
```

#### 2.3 Message Threading System
**Enhance**: `app/services/thread_service.py`

**Add functions:**
- `create_agent_thread()` - Create thread for agent communication
- `append_agent_message()` - Store agent message in `agent_messages` table
- `get_agent_thread_messages()` - Retrieve agent conversation

**Database Integration:**
```python
def append_agent_message(
    thread_id: str,
    agent_id: str,
    role: str,  # 'delegation', 'response', 'feedback'
    message_text: str,
    metadata: Dict = None
):
    db = get_db_service()
    db.execute_update(
        """INSERT INTO agent_messages 
           (thread_id, agent_id, role, message_text, metadata)
           VALUES (%s, %s, %s, %s, %s)""",
        (thread_id, agent_id, role, message_text, Json(metadata or {}))
    )
```

---

### Phase 3: Implement Stage 3 (Self-Review / Feedback Loop)

#### 3.1 Review Service
**File**: `app/services/review_service.py` (new)

**Functions:**
- `review_agent_work()` - DM/CEA reviews agent output
- `generate_feedback()` - Create feedback with score
- `should_retry()` - Determine if feedback warrants retry

**Feedback Scoring:**
```python
@dataclass
class Feedback:
    reviewer: str  # 'maria', 'cea'
    agent_id: str
    score: float  # 0.0 - 1.0
    importance: str  # 'critical', 'high', 'medium', 'low'
    feedback_text: str
    requires_retry: bool

def should_retry(feedback: Feedback, max_iterations: int, current_iteration: int) -> bool:
    if current_iteration >= max_iterations:
        return False
    
    # Critical or high importance feedback always retries (if under max)
    if feedback.importance in ['critical', 'high']:
        return True
    
    # Medium importance: retry if score < 0.7
    if feedback.importance == 'medium' and feedback.score < 0.7:
        return True
    
    # Low importance: retry if score < 0.5
    if feedback.importance == 'low' and feedback.score < 0.5:
        return True
    
    return False
```

#### 3.2 Integrate Review into Autogen Flow
**Modify**: `app/services/autogen_coordinator.py`

**Add review step:**
```python
def run_multi_agent_task_with_review(...):
    # ... agent execution ...
    
    # DM reviews agent work
    feedback = maria.review_agent_work(agent_results)
    
    if should_retry(feedback, max_iterations=3, current_iteration=1):
        # Retry with feedback
        agent_results = execute_agents_with_feedback(agent_tasks, feedback)
    
    # CEA reviews DM aggregation
    cea_feedback = cea.review_dm_work(dm_result)
    
    # ... continue ...
```

---

### Phase 4: Implement Stage 4 (Autonomy)

#### 4.1 Autonomous Task Scheduler
**File**: `app/services/autonomous_scheduler.py` (new)

**Functions:**
- `create_recurring_task()` - Register recurring task
- `check_scheduled_tasks()` - Check if tasks should run
- `execute_autonomous_task()` - Run task without user input

**Task Definition:**
```python
@dataclass
class RecurringTask:
    task_id: str
    description: str
    schedule: Dict  # {"type": "daily", "time": "09:00"}
    department: str
    agent_workflow: List[str]  # ["colby", "sofie", "coco"]
    enabled: bool
    last_run: Optional[datetime]
    next_run: datetime
```

**Scheduler Loop:**
```python
def scheduler_loop():
    while True:
        tasks = get_pending_recurring_tasks()
        for task in tasks:
            if should_run(task):
                execute_autonomous_task(task)
                update_task_last_run(task)
        time.sleep(60)  # Check every minute
```

#### 4.2 Self-Initiated Task Creation
**Enhance**: `app/services/autogen_coordinator.py`

**Add autonomy detection:**
```python
def detect_autonomous_opportunity(context: List[Dict]) -> Optional[Dict]:
    """
    CEA analyzes conversation and detects:
    - Recurring patterns
    - Opportunities for automation
    - Tasks that should be scheduled
    """
    # Use CEA to analyze if task should become recurring
    prompt = f"""Analyze this task and determine if it should be automated/recurring:
    
    {context}
    
    Return JSON: {{"should_automate": true/false, "schedule": {{"type": "daily", "time": "09:00"}}, "reason": "..."}}
    """
    # ... execute with CEA ...
```

#### 4.3 Store Autonomous Tasks
**Database**: Add to `async_tasks` or create `recurring_tasks` table

```sql
CREATE TABLE IF NOT EXISTS recurring_tasks (
    id VARCHAR(255) PRIMARY KEY,
    description TEXT NOT NULL,
    schedule JSONB NOT NULL,
    department VARCHAR(50),
    agent_workflow JSONB,
    enabled BOOLEAN DEFAULT true,
    last_run TIMESTAMP WITH TIME ZONE,
    next_run TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
```

---

## Implementation Order (Recommended)

### Week 1: Foundation (Stage 2 Base)
1. ✅ Create `marketing_agents.py` - Define agent profiles
2. ✅ Create `agent_executor.py` - Execute agents with role prompts
3. ✅ Extend `autogen_coordinator.py` - Add `run_multi_agent_task()`
4. ✅ Test: "Create blog post + X post" with Colby + Sofie

### Week 2: Async Communication (Stage 2 Complete)
1. ✅ Create `dm_service.py` - Maria DM layer
2. ✅ Create `agent_communication.py` - Message passing
3. ✅ Enhance `thread_service.py` - Agent message storage
4. ✅ Test: Full flow CEA → Maria → Agents → Maria → CEA

### Week 3: Review System (Stage 3)
1. ✅ Create `review_service.py` - Feedback/scoring
2. ✅ Integrate review into autogen flow
3. ✅ Test: Maria reviews agent work, provides feedback, agents retry

### Week 4: Autonomy (Stage 4)
1. ✅ Create `autonomous_scheduler.py` - Recurring task system
2. ✅ Add self-initiated task detection
3. ✅ Test: "Create Sleep blog post every day at 9am"

---

## Database Population Strategy

### How Agent Interactions Fill DB

1. **User Chat** → `messages` table (already working)
2. **Agent Messages** → `agent_messages` table
   - CEA → DM delegation
   - DM → Agent instructions
   - Agent → DM results
   - DM → CEA aggregation
3. **Generated Content** → `semantic_memory` table
   - Blog posts, social posts, etc.
   - Tagged with `source_type='agent_generated'`
   - Includes metadata: `{agent: 'colby', task_id: '...', date: '...'}`
4. **Task Tracking** → `async_tasks` table
   - Multi-agent tasks
   - Progress logs
   - Agent insights

### Example: "Create blog post + X post" Flow

```
1. User: "Create blog post + X post about Sleep"
2. CEA analyzes → stores in agent_messages (thread_id: task_123, agent_id: cea)
3. CEA delegates to Maria → stores in agent_messages (thread_id: task_123, agent_id: maria)
4. Maria delegates to Colby → stores in agent_messages (thread_id: task_123, agent_id: colby)
5. Colby generates blog post → stores in semantic_memory (source_type: agent_generated, agent: colby)
6. Maria delegates to Sofie → stores in agent_messages
7. Sofie generates X post → stores in semantic_memory
8. Maria aggregates → stores in agent_messages
9. CEA synthesizes → stores in messages (user-facing)
10. All stored in async_tasks (task_id: task_123)
```

---

## Key Files to Create/Modify

### New Files:
1. `app/services/marketing_agents.py` - Agent profiles
2. `app/services/agent_executor.py` - Agent execution
3. `app/services/dm_service.py` - DM layer
4. `app/services/agent_communication.py` - Message passing
5. `app/services/async_agent_executor.py` - Parallel execution
6. `app/services/review_service.py` - Feedback system
7. `app/services/autonomous_scheduler.py` - Recurring tasks

### Modify Existing:
1. `app/services/autogen_coordinator.py` - Extend for multi-agent
2. `app/services/thread_service.py` - Add agent message functions
3. `app/services/db_service.py` - Add agent_messages CRUD
4. `app/routes/chat.py` - Add multi-agent endpoint (optional)

---

## Testing Strategy

### Stage 2 Test:
```python
# Test: "Create blog post + X post about Sleep"
task = run_multi_agent_task(
    "Create a blog post about Sleep section, along with an X post promoting it",
    department="marketing"
)
# Verify:
# - CEA → Maria delegation stored
# - Maria → Colby + Sofie delegation stored
# - Colby blog post generated and stored
# - Sofie X post generated and stored
# - Maria aggregation stored
# - CEA final response stored
```

### Stage 3 Test:
```python
# Test: Maria reviews Colby's work, provides feedback, Colby retries
# Verify feedback stored in agent_messages
# Verify retry executed
# Verify final improved result
```

### Stage 4 Test:
```python
# Test: "Create Sleep blog post every day at 9am"
# Register recurring task
# Wait for 9am (or manually trigger)
# Verify task executes autonomously
# Verify content generated and stored
```

---

## Next Steps

1. **Start with Phase 1.1**: Create `marketing_agents.py` with agent profiles
2. **Then Phase 1.2**: Extend autogen coordinator for multi-agent
3. **Test incrementally**: Get one agent (Colby) working first
4. **Add DM layer**: Maria coordinates multiple agents
5. **Add review**: Maria reviews and provides feedback
6. **Add autonomy**: Recurring task scheduler

**Focus**: Get Marketing department (Maria + agents) working end-to-end before expanding to other departments.



