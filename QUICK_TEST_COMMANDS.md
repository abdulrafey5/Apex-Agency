# Quick Test Commands Reference

## Essential Commands for EC2 Testing

### 1. Pull Latest Code
```bash
cd /data/inception
git pull origin main
```

### 2. Check Services
```bash
# Ollama
curl http://localhost:11434/api/tags

# Flask App
curl http://localhost:3000/healthz
```

### 3. Quick Component Tests
```bash
# Grok API
curl http://localhost:3000/debug-grok

# CEA Delegation
curl http://localhost:3000/debug-delegation

# Incubator Status
curl http://localhost:3000/incubator-status
```

### 4. Test Chat (Local CEA)
```bash
curl -X POST http://localhost:3000/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "Hello, how are you?"}'
```

### 5. Start Incubator Session
```bash
curl -X POST http://localhost:3000/incubator \
  -H "Content-Type: application/json" \
  -d '{"business_idea": "An AI app for coffee shop recommendations"}'
```

### 6. Check Incubator Progress
```bash
# Replace TASK_ID with actual task ID
curl http://localhost:3000/incubator-result/TASK_ID
```

### 7. Check Logs
```bash
# Application logs
tail -f app/logs/app.log

# Errors only
grep -i error app/logs/app.log | tail -20

# Incubator logs
grep -i incubator app/logs/app.log | tail -20
```

### 8. Check Memory
```bash
# View memory file
cat storage/instructions/memory.yaml

# Check session count
grep -c "session_id" storage/instructions/memory.yaml
```

### 9. Run Full Test Script
```bash
chmod +x test_full_flow.sh
./test_full_flow.sh
```

---

## Environment Variables Quick Check
```bash
# Check all incubator-related vars
env | grep INCUBATOR

# Check Ollama vars
env | grep OLLAMA

# Check Grok vars
env | grep GROK
```

---

## Restart Services
```bash
# Restart Ollama
sudo systemctl restart ollama

# Restart Flask (if using systemd)
sudo systemctl restart inception-app

# Or manually
cd /data/inception/app
source ../venv/bin/activate
python main.py
```

---

## Common Issues & Quick Fixes

### Port 3000 in use
```bash
sudo lsof -i :3000
sudo kill -9 <PID>
```

### Ollama not responding
```bash
ollama serve &
# OR
sudo systemctl start ollama
```

### Memory file permissions
```bash
mkdir -p storage/instructions
chmod 755 storage/instructions
touch storage/instructions/memory.yaml
chmod 644 storage/instructions/memory.yaml
```

