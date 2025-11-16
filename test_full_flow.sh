#!/bin/bash

# Complete Testing Script for EC2 Instance
# Usage: ./test_full_flow.sh

BASE_URL="http://localhost:3000"
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo "=========================================="
echo "  Complete Flow Testing Script"
echo "=========================================="
echo ""

# Test 1: Health Check
echo -e "${YELLOW}[1/9]${NC} Testing Health Check..."
HEALTH=$(curl -s $BASE_URL/healthz)
if echo "$HEALTH" | grep -q "ok"; then
    echo -e "${GREEN}✓${NC} Health check passed"
else
    echo -e "${RED}✗${NC} Health check failed: $HEALTH"
    exit 1
fi
echo ""

# Test 2: Grok Connection
echo -e "${YELLOW}[2/9]${NC} Testing Grok API Connection..."
GROK_RESPONSE=$(curl -s $BASE_URL/debug-grok)
if echo "$GROK_RESPONSE" | grep -q "working"; then
    echo -e "${GREEN}✓${NC} Grok API is working"
else
    echo -e "${RED}✗${NC} Grok API test failed"
    echo "$GROK_RESPONSE" | head -5
fi
echo ""

# Test 3: CEA Delegation
echo -e "${YELLOW}[3/9]${NC} Testing CEA Delegation System..."
DELEGATION=$(curl -s $BASE_URL/debug-delegation)
if echo "$DELEGATION" | grep -q "tests_completed"; then
    echo -e "${GREEN}✓${NC} CEA delegation system working"
else
    echo -e "${YELLOW}⚠${NC} CEA delegation test incomplete"
fi
echo ""

# Test 4: Incubator Status
echo -e "${YELLOW}[4/9]${NC} Testing Incubator Status..."
STATUS_RESPONSE=$(curl -s $BASE_URL/incubator-status)
AGENT_COUNT=$(echo "$STATUS_RESPONSE" | grep -o '"total_agents":[0-9]*' | grep -o '[0-9]*')
if [ ! -z "$AGENT_COUNT" ] && [ "$AGENT_COUNT" -ge 5 ]; then
    echo -e "${GREEN}✓${NC} Incubator status OK - $AGENT_COUNT agents available"
else
    echo -e "${RED}✗${NC} Incubator status check failed"
    echo "$STATUS_RESPONSE" | head -10
fi
echo ""

# Test 5: Simple Chat (Local CEA)
echo -e "${YELLOW}[5/9]${NC} Testing Local CEA (Ollama)..."
CHAT_RESPONSE=$(curl -s -X POST $BASE_URL/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "Say hello in one word"}')
if echo "$CHAT_RESPONSE" | grep -q "response"; then
    echo -e "${GREEN}✓${NC} Local CEA is responding"
    echo "Response preview: $(echo "$CHAT_RESPONSE" | grep -o '"response":"[^"]*' | head -1 | cut -d'"' -f4 | cut -c1-50)..."
else
    echo -e "${RED}✗${NC} Local CEA test failed"
fi
echo ""

# Test 6: Start Incubator Session
echo -e "${YELLOW}[6/9]${NC} Starting Incubator Session..."
INCUBATOR_RESPONSE=$(curl -s -X POST $BASE_URL/incubator \
  -H "Content-Type: application/json" \
  -d '{"business_idea": "An AI-powered app that helps people find the best coffee shops based on their preferences and location"}')

TASK_ID=$(echo "$INCUBATOR_RESPONSE" | grep -o '"task_id":"[^"]*' | cut -d'"' -f4)

if [ -z "$TASK_ID" ]; then
    echo -e "${RED}✗${NC} Failed to start incubator session"
    echo "$INCUBATOR_RESPONSE"
    exit 1
fi

echo -e "${GREEN}✓${NC} Incubator session started"
echo "Task ID: $TASK_ID"
echo ""

# Test 7: Monitor Incubator Progress
echo -e "${YELLOW}[7/9]${NC} Monitoring Incubator Progress..."
echo "This may take 5-10 minutes. Checking every 15 seconds..."
echo ""

MAX_CHECKS=40
CHECK_COUNT=0
COMPLETED=false

while [ $CHECK_COUNT -lt $MAX_CHECKS ]; do
    CHECK_COUNT=$((CHECK_COUNT + 1))
    RESULT=$(curl -s $BASE_URL/incubator-result/$TASK_ID)
    CURRENT_STATUS=$(echo "$RESULT" | grep -o '"status":"[^"]*' | cut -d'"' -f4)
    
    if [ "$CURRENT_STATUS" = "completed" ]; then
        echo -e "${GREEN}✓${NC} Incubator session completed!"
        COMPLETED=true
        break
    elif [ "$CURRENT_STATUS" = "failed" ]; then
        echo -e "${RED}✗${NC} Incubator session failed"
        ERROR=$(echo "$RESULT" | grep -o '"error":"[^"]*' | cut -d'"' -f4)
        echo "Error: $ERROR"
        exit 1
    else
        PROGRESS_COUNT=$(echo "$RESULT" | grep -o '"progress_log":\[.*\]' | grep -o '\[.*\]' | grep -o '\]' | wc -l)
        echo "[Check $CHECK_COUNT/$MAX_CHECKS] Status: $CURRENT_STATUS (Progress entries: $PROGRESS_COUNT)"
    fi
    
    sleep 15
done

if [ "$COMPLETED" = false ]; then
    echo -e "${YELLOW}⚠${NC} Session still running after $MAX_CHECKS checks. Check manually with:"
    echo "curl $BASE_URL/incubator-result/$TASK_ID"
fi
echo ""

# Test 8: Verify Results
echo -e "${YELLOW}[8/9]${NC} Verifying Incubator Results..."
FINAL_RESULT=$(curl -s $BASE_URL/incubator-result/$TASK_ID)
AGENT_COUNT=$(echo "$FINAL_RESULT" | grep -o '"agent_insights":{[^}]*}' | grep -o '"[^"]*":{' | wc -l)
HAS_PLAN=$(echo "$FINAL_RESULT" | grep -q '"business_plan"' && echo "yes" || echo "no")

if [ "$AGENT_COUNT" -ge 5 ]; then
    echo -e "${GREEN}✓${NC} All agents provided insights ($AGENT_COUNT agents)"
else
    echo -e "${YELLOW}⚠${NC} Only $AGENT_COUNT agents provided insights"
fi

if [ "$HAS_PLAN" = "yes" ]; then
    PLAN_LENGTH=$(echo "$FINAL_RESULT" | grep -o '"business_plan":"[^"]*' | cut -d'"' -f4 | wc -c)
    echo -e "${GREEN}✓${NC} Business plan generated ($PLAN_LENGTH characters)"
else
    echo -e "${RED}✗${NC} Business plan not found"
fi
echo ""

# Test 9: Check Memory Storage
echo -e "${YELLOW}[9/9]${NC} Verifying Memory Storage..."
if [ -f "storage/instructions/memory.yaml" ]; then
    SESSION_COUNT=$(grep -c "session_id" storage/instructions/memory.yaml 2>/dev/null || echo "0")
    if [ "$SESSION_COUNT" -gt 0 ]; then
        echo -e "${GREEN}✓${NC} Memory file exists with $SESSION_COUNT session(s)"
    else
        echo -e "${YELLOW}⚠${NC} Memory file exists but no sessions found yet"
    fi
else
    echo -e "${RED}✗${NC} Memory file not found at storage/instructions/memory.yaml"
fi
echo ""

# Summary
echo "=========================================="
echo "  Test Summary"
echo "=========================================="
echo "Task ID: $TASK_ID"
echo "View full results: curl $BASE_URL/incubator-result/$TASK_ID"
echo ""
echo "All tests completed!"

