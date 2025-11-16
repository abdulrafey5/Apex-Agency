# Complete Testing Guide for EC2 Instance

## Prerequisites
- EC2 instance with gpt-oss:20b model running via Ollama
- GitHub repository with latest code
- Python virtual environment
- Required environment variables configured

---

## Step 1: Pull Latest Code from GitHub

```bash
# SSH into your EC2 instance
ssh ubuntu@your-ec2-ip

# Navigate to your project directory
cd /data/inception  # or wherever your project is located

# Check current branch and status
git status
git branch

# Pull latest changes
git pull origin main  # or your branch name

# Verify files are updated
ls -la app/services/incubator_orchestrator.py
ls -la app/services/incubator_agents.py
```

---

## Step 2: Verify Environment Setup

```bash
# Activate virtual environment
source venv/bin/activate  # or your venv path

# Verify Python version
python --version  # Should be 3.8+

# Check if required packages are installed
pip list | grep -E "flask|requests|pyyaml|ollama"

# Verify .env file exists and has required variables
cat app/.env | grep -E "OLLAMA|GROK|INCUBATOR|CEA"
```

### Required Environment Variables (check in app/.env):
```bash
# Ollama Configuration
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=gpt-oss:20b
OLLAMA_MAX_TOKENS=700
OLLAMA_NUM_GPU=0

# Grok Configuration
GROK_API_KEY=your_grok_api_key
GROK_MODEL=grok-4-fast

# CEA Configuration
CEA_MAX_TOKENS=700
CEA_CONTINUE_TOKENS=400
CEA_USE_GROK_FOR_CONTINUATION=true
CEA_USE_GROK_FOR_SYNTHESIS=false

# Incubator Configuration
INCUBATOR_DURATION_MINUTES=60
INCUBATOR_WRAP_UP_MINUTES=5
INCUBATOR_AGENT_TIMEOUT_SECONDS=300
INCUBATOR_USE_GROK_FOR_AGENTS=false
INCUBATOR_USE_GROK_FOR_SYNTHESIS=false
```

---

## Step 3: Verify Services are Running

### 3.1 Check Ollama Service
```bash
# Check if Ollama is running
curl http://localhost:11434/api/tags

# Test if gpt-oss:20b model is available
curl http://localhost:11434/api/show -d '{"name": "gpt-oss:20b"}'

# Quick test generation
curl http://localhost:11434/api/generate -d '{
  "model": "gpt-oss:20b",
  "prompt": "Say hello",
  "stream": false,
  "num_predict": 10
}'
```

### 3.2 Check Flask Application
```bash
# Check if Flask app is running (if already started)
curl http://localhost:3000/healthz

# If not running, start it (in a separate terminal or screen/tmux)
cd /data/inception/app
source ../venv/bin/activate
python main.py
# OR if using gunicorn:
# gunicorn -w 4 -b 0.0.0.0:3000 main:app
```

---

## Step 4: Test Individual Components

### 4.1 Test Grok API Connection
```bash
curl http://localhost:3000/debug-grok
```

**Expected Response:**
```json
{
  "status": "working",
  "response": "Hello! I'm Grok..."
}
```

### 4.2 Test CEA Delegation System
```bash
curl http://localhost:3000/debug-delegation
```

**Expected Response:**
```json
{
  "api_status": "working",
  "delegation_analysis": {...},
  "direct_grok_test": "...",
  "simple_cea_test": "...",
  "tests_completed": true
}
```

### 4.3 Test Local CEA (Ollama) Directly
```bash
# Test simple chat with CEA
curl -X POST http://localhost:3000/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "What is 2+2? Answer briefly."}'
```

**Expected:** Response from local CEA model

---

## Step 5: Test Incubator System

### 5.1 Check Incubator Status
```bash
curl http://localhost:3000/incubator-status
```

**Expected Response:**
```json
{
  "status": "operational",
  "configuration": {
    "duration_minutes": 60,
    "wrap_up_minutes": 5,
    "agent_timeout_seconds": 300,
    "use_grok_for_agents": false,
    "use_grok_for_synthesis": false,
    "available_agents": [
      {
        "role": "marketing_expert",
        "name": "Marketing Strategist",
        "expertise": "..."
      },
      ...
    ],
    "total_agents": 5
  }
}
```

### 5.2 Start an Incubator Session
```bash
# Start a test incubator session
curl -X POST http://localhost:3000/incubator \
  -H "Content-Type: application/json" \
  -d '{
    "business_idea": "An AI-powered app that helps people find the best coffee shops based on their preferences and location"
  }'
```

**Expected Response:**
```json
{
  "task_id": "uuid-here",
  "status": "queued",
  "message": "Incubator session started. Use /incubator-result/<task_id> to check progress.",
  "estimated_duration_minutes": 60
}
```

**Save the task_id from the response!**

### 5.3 Monitor Incubator Progress
```bash
# Replace TASK_ID with the task_id from step 5.2
TASK_ID="your-task-id-here"

# Check progress (run this multiple times)
curl http://localhost:3000/incubator-result/$TASK_ID
```

**Expected Response (while running):**
```json
{
  "status": "processing",
  "progress_log": [
    "[14:55:32] Starting incubator session...",
    "[14:55:32] Running Marketing Strategist analysis...",
    ...
  ],
  "type": "incubator"
}
```

**Expected Response (when completed):**
```json
{
  "status": "completed",
  "session_id": "...",
  "business_idea": "...",
  "agent_insights": {
    "marketing_expert": {
      "agent_name": "Marketing Strategist",
      "status": "completed",
      "insight": "..."
    },
    ...
  },
  "business_plan": "...",
  "progress_log": [...],
  "duration_minutes": 5,
  "completed_agents": 5
}
```

---

## Step 6: Verify Memory Storage

### 6.1 Check Memory File
```bash
# Check if memory.yaml exists and has incubator data
cat storage/instructions/memory.yaml

# Or check specific sections
cat storage/instructions/memory.yaml | grep -A 5 "incubator_sessions"
```

**Expected:** Should contain `incubator_sessions` and `agent_insights_history` sections

### 6.2 Verify Memory is Being Used
```bash
# Start a second incubator session with similar idea
curl -X POST http://localhost:3000/incubator \
  -H "Content-Type: application/json" \
  -d '{
    "business_idea": "A mobile app for finding coffee shops"
  }'

# Check if agents reference previous session in their analysis
# (This will be visible in the agent insights)
```

---

## Step 7: Full End-to-End Test Script

Create a test script `test_full_flow.sh`:

```bash
#!/bin/bash

BASE_URL="http://localhost:3000"
echo "=== Testing Complete Flow ==="

echo "1. Testing Health Check..."
curl -s $BASE_URL/healthz
echo -e "\n"

echo "2. Testing Grok Connection..."
curl -s $BASE_URL/debug-grok | jq .
echo -e "\n"

echo "3. Testing CEA Delegation..."
curl -s $BASE_URL/debug-delegation | jq .
echo -e "\n"

echo "4. Testing Incubator Status..."
curl -s $BASE_URL/incubator-status | jq .
echo -e "\n"

echo "5. Starting Incubator Session..."
RESPONSE=$(curl -s -X POST $BASE_URL/incubator \
  -H "Content-Type: application/json" \
  -d '{"business_idea": "An AI-powered fitness app that creates personalized workout plans"}')

TASK_ID=$(echo $RESPONSE | jq -r '.task_id')
echo "Task ID: $TASK_ID"
echo -e "\n"

echo "6. Monitoring Progress (checking every 10 seconds)..."
for i in {1..30}; do
  echo "Check $i:"
  STATUS=$(curl -s $BASE_URL/incubator-result/$TASK_ID | jq -r '.status')
  echo "Status: $STATUS"
  
  if [ "$STATUS" = "completed" ] || [ "$STATUS" = "failed" ]; then
    echo "Session finished!"
    curl -s $BASE_URL/incubator-result/$TASK_ID | jq .
    break
  fi
  
  sleep 10
done

echo -e "\n7. Checking Memory Storage..."
if [ -f "storage/instructions/memory.yaml" ]; then
  echo "Memory file exists"
  echo "Recent sessions:"
  grep -A 2 "session_id" storage/instructions/memory.yaml | head -10
else
  echo "Memory file not found!"
fi

echo -e "\n=== Test Complete ==="
```

**Make it executable and run:**
```bash
chmod +x test_full_flow.sh
./test_full_flow.sh
```

---

## Step 8: Check Logs for Errors

```bash
# Check application logs
tail -f app/logs/app.log

# Check for errors
grep -i error app/logs/app.log | tail -20

# Check incubator-specific logs
grep -i incubator app/logs/app.log | tail -20

# Check for memory-related logs
grep -i memory app/logs/app.log | tail -20
```

---

## Step 9: Quick Verification Checklist

- [ ] Code pulled from GitHub successfully
- [ ] Virtual environment activated
- [ ] All environment variables set correctly
- [ ] Ollama service running and gpt-oss:20b model available
- [ ] Flask application running on port 3000
- [ ] Grok API connection working (`/debug-grok`)
- [ ] CEA delegation working (`/debug-delegation`)
- [ ] Local CEA (Ollama) responding (`/chat`)
- [ ] Incubator status endpoint working (`/incubator-status`)
- [ ] Incubator session can be started (`/incubator`)
- [ ] Incubator session completes successfully
- [ ] All 5 agents provide insights
- [ ] Business plan is generated
- [ ] Memory is saved to `memory.yaml`
- [ ] No errors in logs

---

## Troubleshooting

### Issue: Ollama not responding
```bash
# Restart Ollama
sudo systemctl restart ollama
# OR
ollama serve
```

### Issue: Flask app not starting
```bash
# Check if port 3000 is in use
sudo lsof -i :3000

# Check Python dependencies
pip install -r requirements.txt
```

### Issue: Incubator session fails
```bash
# Check logs
tail -50 app/logs/app.log

# Verify model is accessible
curl http://localhost:11434/api/generate -d '{"model": "gpt-oss:20b", "prompt": "test", "stream": false}'
```

### Issue: Memory not saving
```bash
# Check file permissions
ls -la storage/instructions/memory.yaml

# Check if directory exists
mkdir -p storage/instructions
chmod 755 storage/instructions
```

---

## Expected Test Results

### Successful Test Output:
1. **Health Check**: `{"status": "ok"}`
2. **Grok Test**: Response with "working" status
3. **CEA Test**: Response with insights
4. **Incubator Status**: Shows 5 available agents
5. **Incubator Session**: Completes in ~5-10 minutes (with local model)
6. **Agent Insights**: All 5 agents provide analysis
7. **Business Plan**: Complete plan generated
8. **Memory**: Session saved to `memory.yaml`

---

## Performance Benchmarks

- **Local CEA Response**: 5-15 seconds
- **Grok Response**: 2-5 seconds
- **Single Agent Analysis**: 30-60 seconds (local), 5-10 seconds (Grok)
- **Full Incubator Session**: 5-10 minutes (local agents), 2-3 minutes (Grok agents)
- **Memory Save**: < 1 second

---

## Next Steps After Testing

1. If all tests pass: System is ready for production use
2. If tests fail: Check logs and troubleshoot specific components
3. Monitor memory usage: Check `memory.yaml` size over time
4. Optimize: Adjust timeouts and token limits based on performance

