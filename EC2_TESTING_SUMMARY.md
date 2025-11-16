# EC2 Testing Summary - Quick Start

## 🚀 Quick Start Steps

### Step 1: SSH into EC2 and Pull Code
```bash
ssh ubuntu@your-ec2-ip
cd /data/inception
git pull origin main
source venv/bin/activate
```

### Step 2: Verify Services
```bash
# Check Ollama
curl http://localhost:11434/api/tags

# Check Flask (if running)
curl http://localhost:3000/healthz
```

### Step 3: Run Full Test
```bash
# Make script executable (on EC2/Linux)
chmod +x test_full_flow.sh

# Run the test
./test_full_flow.sh
```

---

## 📋 Manual Testing Steps

### 1. Test Individual Components
```bash
# Test Grok
curl http://localhost:3000/debug-grok

# Test CEA
curl http://localhost:3000/debug-delegation

# Test Incubator Status
curl http://localhost:3000/incubator-status
```

### 2. Start Incubator Session
```bash
curl -X POST http://localhost:3000/incubator \
  -H "Content-Type: application/json" \
  -d '{"business_idea": "An AI app for coffee shop recommendations"}'
```

**Save the `task_id` from response!**

### 3. Monitor Progress
```bash
# Replace TASK_ID with your task ID
curl http://localhost:3000/incubator-result/TASK_ID
```

### 4. Check Memory
```bash
cat storage/instructions/memory.yaml | grep -A 5 "incubator_sessions"
```

---

## ✅ Success Criteria

- [x] All endpoints respond without errors
- [x] Incubator session starts successfully
- [x] All 5 agents provide insights
- [x] Business plan is generated
- [x] Memory is saved to `memory.yaml`
- [x] No errors in logs

---

## 📁 Files Created

1. **TESTING_GUIDE.md** - Complete detailed testing guide
2. **test_full_flow.sh** - Automated test script
3. **QUICK_TEST_COMMANDS.md** - Quick reference for commands
4. **EC2_TESTING_SUMMARY.md** - This file

---

## 🔍 What to Check

1. **Ollama Service**: `curl http://localhost:11434/api/tags`
2. **Flask App**: `curl http://localhost:3000/healthz`
3. **Grok API**: `curl http://localhost:3000/debug-grok`
4. **Local CEA**: `curl -X POST http://localhost:3000/chat -H "Content-Type: application/json" -d '{"message":"test"}'`
5. **Incubator**: Start session and monitor progress
6. **Memory**: Check `storage/instructions/memory.yaml`

---

## ⚠️ Common Issues

- **Ollama not running**: `sudo systemctl restart ollama`
- **Port 3000 in use**: `sudo lsof -i :3000` then kill process
- **Memory file missing**: `mkdir -p storage/instructions`
- **Permission errors**: `chmod 755 storage/instructions`

---

## 📊 Expected Timeline

- **Component Tests**: 1-2 minutes
- **Incubator Session**: 5-10 minutes (with local model)
- **Full Test Script**: 10-15 minutes

---

For detailed instructions, see **TESTING_GUIDE.md**

