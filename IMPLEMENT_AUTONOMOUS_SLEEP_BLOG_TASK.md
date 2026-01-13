# Implementation Guide: Autonomous Daily Sleep Blog Post Task

## Current State Analysis

### ✅ What Exists:
1. **Agent Zero Runner** (`app/services/agent_zero_runner.py`)
   - Scheduler that checks for agents to run every 60 seconds
   - Supports daily schedules (e.g., "09:00")
   - Currently just simulates tasks with `time.sleep(2)` - **NOT ACTUALLY EXECUTING AI TASKS**

2. **SOP Stage 4 Documentation** (`app/scripts/seed_kb.py`)
   - Already describes exactly what you want:
   - "Create a new post for the Sleep section of the blog every day at 9am and send word about it through all free channels"
   - 5-step workflow: Draft → Creative → Social → QA → Publish

3. **AI Generation Services**:
   - `cea_delegation_service.py` - Main AI task delegation
   - `chunked_generation_service.py` - Handles multi-part content (blog + social posts)
   - `rag_service.py` - Can retrieve SOPs and agent library for context

4. **Database Storage**:
   - `semantic_memory` table - Can store generated content with `source_type='agent_generated'`
   - `async_tasks` table - Can track task execution

### ❌ What's Missing:
1. **Agent YAML Configuration** - No agent file exists for Sleep blog content
2. **Task Execution Logic** - `perform_task()` doesn't call AI services
3. **Content Storage** - Generated content isn't being saved to semantic_memory
4. **Service Integration** - Agent Zero Runner doesn't import/use CEA services

---

## Implementation Steps

### Step 1: Create Agent YAML File

**Location:** `/data/inception/storage/instructions/agents/sleep_blog_content.yaml`

**Content:**
```yaml
name: Sleep Blog Content Agent
department: Marketing
schedule:
  type: daily
  time: "09:00"  # 9am local time (adjust timezone handling if needed)
tasks:
  - id: daily_sleep_post
    description: "Create a new post for the Sleep section of the blog every day at 9am and send word about it through all free channels"
    enabled: true
    type: stage_4_recurring
    workflow:
      - step: draft
        deliverable: blog_post
        agent: Colby  # Copywriting Specialist
      - step: creative
        deliverable: image_guidance
        agent: Coco  # Content Creation Specialist
      - step: social
        deliverable: social_posts
        agent: Sofie  # Social Media Specialist
        channels: ["X", "LinkedIn", "Instagram"]
      - step: qa
        deliverable: review_checklist
        agent: Maria  # Marketing Lead
      - step: publish
        deliverable: published_content
memory:
  last_run: null
  last_post_date: null
  post_count: 0
```

**Note:** The `agent_zero_runner.py` expects agents in `/data/inception/storage/instructions/agents/` but your codebase uses relative paths. You'll need to:
- Either update the ROOT path in `agent_zero_runner.py` to match your deployment
- Or create the directory structure: `storage/instructions/agents/`

---

### Step 2: Enhance `perform_task()` to Execute AI Tasks

**File:** `app/services/agent_zero_runner.py`

**Current Code (Line 58-66):**
```python
def perform_task(agent, memory):
    name = agent.get("name", "Unnamed Agent")
    logging.info(f"🤖 Executing {name} tasks...")
    for task in agent.get("tasks", []):
        if task.get("enabled", True):
            logging.info(f"🧩 Running task: {task['id']} — {task.get('description','No description')}")
            time.sleep(2)  # Simulate task logic; replace with actual API calls
    logging.info(f"✅ Completed {name} cycle.")
    agent.setdefault("memory", {})["last_run"] = datetime.now(timezone.utc).isoformat()
```

**What to Change:**

1. **Import Required Services:**
```python
import sys
from pathlib import Path

# Add app directory to path so we can import services
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from services.cea_delegation_service import delegate_cea_task
from services.chunked_generation_service import generate_chunked_content
from services.rag_service import query_semantic_memory, index_content
from services.db_service import get_db_service
```

2. **Replace `perform_task()` with actual AI execution:**
```python
def perform_task(agent, memory):
    name = agent.get("name", "Unnamed Agent")
    logging.info(f"🤖 Executing {name} tasks...")
    
    # Get RAG context (SOP Stage 4 workflow)
    sop_context = query_semantic_memory(
        "Stage 4 Recurring Task Daily 9am Sleep blog post workflow",
        top_k=3
    )
    context_text = "\n".join([doc["content"] for doc in sop_context])
    
    for task in agent.get("tasks", []):
        if not task.get("enabled", True):
            continue
            
        task_id = task.get("id", "unknown")
        task_desc = task.get("description", "")
        logging.info(f"🧩 Running task: {task_id} — {task_desc}")
        
        try:
            # Build prompt with SOP context
            prompt = f"""You are executing a Stage 4 recurring task.

SOP Context:
{context_text}

Task: {task_desc}

Follow the Stage 4 workflow:
1) Draft: Topic selection (Sleep), outline, write, light SEO, CTA.
2) Creative: Static image guidance; optional short clip.
3) Social: Schedule X/LinkedIn/Instagram posts aligned to publish time; add UTM links.
4) QA: Links, images, tags/hashtags, accessibility (alt text), approvals.
5) Publish & Monitor: Confirm publish; check early metrics; log performance.

Generate the complete content package: blog post + X post + LinkedIn post + Instagram post.
"""
            
            # Use chunked generation for multi-part content
            thread_context = []  # Empty context for autonomous task
            result = generate_chunked_content(prompt, thread_context, use_grok=True)
            
            if result:
                # Store generated content in semantic_memory
                db = get_db_service()
                today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
                source_id = f"sleep_blog_{today}_{task_id}"
                
                # Index the generated content
                index_content(
                    content=result,
                    metadata={
                        "agent": name,
                        "task_id": task_id,
                        "date": today,
                        "workflow": "stage_4",
                        "section": "sleep"
                    },
                    source_type="agent_generated",
                    source_id=source_id
                )
                
                logging.info(f"✅ Task {task_id} completed and stored: {source_id}")
                
                # Update agent memory
                agent_memory = agent.setdefault("memory", {})
                agent_memory["last_run"] = datetime.now(timezone.utc).isoformat()
                agent_memory["last_post_date"] = today
                agent_memory["post_count"] = agent_memory.get("post_count", 0) + 1
            else:
                logging.error(f"❌ Task {task_id} failed: No content generated")
                
        except Exception as e:
            logging.exception(f"❌ Task {task_id} failed: {e}")
    
    logging.info(f"✅ Completed {name} cycle.")
```

---

### Step 3: Fix Path Issues in Agent Zero Runner

**Current Issue:** Hardcoded path `/data/inception` won't work in your deployment.

**File:** `app/services/agent_zero_runner.py`

**Change Line 10:**
```python
# OLD:
ROOT = Path("/data/inception")

# NEW:
ROOT = Path(__file__).resolve().parent.parent.parent  # Points to project root
# Or use environment variable:
ROOT = Path(os.getenv("INCEPTION_ROOT", str(Path(__file__).resolve().parent.parent.parent)))
```

**Update paths:**
```python
AGENTS_DIR = ROOT / "storage" / "instructions" / "agents"
DMS_DIR = ROOT / "storage" / "instructions" / "dms"
MEMORY_FILE = ROOT / "storage" / "instructions" / "memory.yaml"
LOG_FILE = ROOT / "app" / "logs" / "agentzero.log"
```

---

### Step 4: Ensure Agent Zero Runner Runs as a Service

**On EC2, you need to:**

1. **Create systemd service file:** `/etc/systemd/system/agent-zero.service`
```ini
[Unit]
Description=Agent Zero Runner - Autonomous AI Agent Scheduler
After=network.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/opt/inception/app
Environment="PYTHONPATH=/opt/inception/app"
Environment="INCEPTION_ROOT=/opt/inception"
ExecStart=/usr/bin/python3 /opt/inception/app/services/agent_zero_runner.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

2. **Enable and start:**
```bash
sudo systemctl daemon-reload
sudo systemctl enable agent-zero
sudo systemctl start agent-zero
sudo systemctl status agent-zero
```

---

### Step 5: Handle Timezone Correctly

**Issue:** The scheduler uses UTC, but you want 9am local time.

**Fix in `should_run()` function:**

```python
def should_run(schedule, last_run):
    """Return True if agent or DM should run now (daily schedule only)."""
    # Get local timezone (or use env var)
    import pytz
    local_tz = pytz.timezone(os.getenv("TZ", "America/New_York"))  # Adjust to your timezone
    now_local = datetime.now(local_tz)
    
    if schedule.get("type") == "daily":
        run_hour, run_minute = map(int, schedule.get("time", "10:00").split(":"))
        run_time = now_local.replace(hour=run_hour, minute=run_minute, second=0, microsecond=0)
        
        # Run if never run today
        if last_run is None:
            return now_local >= run_time
        
        # Convert last_run to local timezone for comparison
        if isinstance(last_run, str):
            last_run_dt = datetime.fromisoformat(last_run.replace("Z", "+00:00"))
        else:
            last_run_dt = last_run
            
        if last_run_dt.tzinfo is None:
            last_run_dt = pytz.utc.localize(last_run_dt)
        last_run_local = last_run_dt.astimezone(local_tz)
        
        # Run if it's a new day and we're past the scheduled time
        if now_local.date() > last_run_local.date():
            return now_local >= run_time
    
    return False
```

---

### Step 6: Test the Implementation

**Manual Test (without waiting for 9am):**

1. **Create test agent YAML** with schedule time set to current time + 1 minute
2. **Run agent_zero_runner.py manually:**
```bash
cd /opt/inception/app
python3 services/agent_zero_runner.py
```

3. **Check logs:**
```bash
tail -f app/logs/agentzero.log
```

4. **Verify content in database:**
```sql
SELECT source_id, content, metadata, created_at 
FROM semantic_memory 
WHERE source_type = 'agent_generated' 
ORDER BY created_at DESC 
LIMIT 5;
```

---

## Architecture Flow

```
┌─────────────────────────────────────────────────────────────┐
│ Agent Zero Runner (Scheduler)                              │
│ - Runs every 60 seconds                                     │
│ - Checks if agent should run based on schedule             │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│ perform_task()                                              │
│ - Loads agent YAML                                         │
│ - Retrieves SOP Stage 4 context via RAG                    │
│ - Builds prompt with workflow instructions                  │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│ generate_chunked_content()                                  │
│ - Detects multi-part request (blog + social posts)         │
│ - Generates blog post                                       │
│ - Generates X post                                          │
│ - Generates LinkedIn post                                   │
│ - Generates Instagram post                                  │
│ - Combines into final response                              │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│ index_content() → semantic_memory table                    │
│ - Stores generated content                                  │
│ - Creates embeddings                                        │
│ - Tags with source_type='agent_generated'                  │
│ - Includes metadata (date, agent, task_id)                 │
└─────────────────────────────────────────────────────────────┘
```

---

## Next Steps (Future Enhancements)

1. **Actual Publishing Integration:**
   - Connect to blog CMS API (WordPress, Ghost, etc.)
   - Connect to social media APIs (Twitter/X, LinkedIn, Instagram)
   - Schedule posts via Buffer/Hootsuite API

2. **Content Queueing:**
   - SOP says "queue posts 3 days ahead"
   - Implement a queue system that generates 3 days of content at once

3. **QA & Approval Workflow:**
   - Store generated content in "pending" status
   - Maria (Marketing Lead) reviews via admin interface
   - Auto-publish after approval or manual publish

4. **Performance Monitoring:**
   - Track metrics (views, engagement) for published posts
   - Store in `async_tasks.result_data` or new `content_metrics` table
   - Use feedback to improve future content generation

5. **Multi-Section Support:**
   - Extend to other blog sections (Mindfulness, Nutrition, Exercise)
   - Create separate agent YAML files for each section
   - Different schedules per section

---

## Key Files to Modify

1. ✅ `app/services/agent_zero_runner.py` - Enhance `perform_task()`
2. ✅ `storage/instructions/agents/sleep_blog_content.yaml` - Create agent config
3. ✅ `/etc/systemd/system/agent-zero.service` - Create systemd service (on EC2)
4. ⚠️ `app/services/rag_service.py` - Verify `index_content()` supports `source_type` parameter
5. ⚠️ `app/services/chunked_generation_service.py` - Verify it handles Stage 4 workflow prompts

---

## Testing Checklist

- [ ] Agent YAML file created and validated
- [ ] `perform_task()` imports and calls AI services successfully
- [ ] Generated content appears in `semantic_memory` table
- [ ] Agent Zero Runner service runs continuously
- [ ] Scheduler triggers at correct time (9am local)
- [ ] Content includes blog post + all social posts
- [ ] Logs show successful execution
- [ ] No errors in `agentzero.log`

---

## Troubleshooting

**Issue:** Agent Zero Runner can't import services
- **Fix:** Ensure `PYTHONPATH` includes `/opt/inception/app` in systemd service

**Issue:** Timezone mismatch (runs at wrong time)
- **Fix:** Set `TZ` environment variable in systemd service file

**Issue:** Generated content not stored
- **Fix:** Check `index_content()` function signature - may need to pass `source_type` explicitly

**Issue:** Chunked generation not working
- **Fix:** Verify `generate_chunked_content()` detects multi-part requests correctly

**Issue:** Agent runs multiple times per day
- **Fix:** Check `should_run()` logic - ensure `last_run` comparison works correctly



