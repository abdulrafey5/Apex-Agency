# Quick Deployment Guide

## ✅ Everything is Ready!

All code changes are complete and tested. Here's the deployment process:

---

## 🚀 Step-by-Step Deployment

### **LOCAL (Your Machine)**

#### 1. Build Docker Image
```bash
docker build -t inception-app:latest -f Dockerfile .
```

#### 2. Tag for ECR
```bash
docker tag inception-app:latest \
  421730342685.dkr.ecr.eu-north-1.amazonaws.com/inception-app:latest
```

#### 3. Login to ECR
```bash
aws ecr get-login-password --region eu-north-1 | \
  docker login --username AWS --password-stdin \
  421730342685.dkr.ecr.eu-north-1.amazonaws.com
```

#### 4. Push to ECR
```bash
docker push \
  421730342685.dkr.ecr.eu-north-1.amazonaws.com/inception-app:latest
```

---

### **EC2 SERVER**

#### 5. SSH to EC2
```bash
ssh ubuntu@your-ec2-ip
```

#### 6. Navigate to Project
```bash
cd /opt/inception  # or your project path
```

#### 7. Login to ECR on EC2
```bash
aws ecr get-login-password --region eu-north-1 | \
  docker login --username AWS --password-stdin \
  421730342685.dkr.ecr.eu-north-1.amazonaws.com
```

#### 8. Pull Latest Image
```bash
docker pull \
  421730342685.dkr.ecr.eu-north-1.amazonaws.com/inception-app:latest
```

#### 9. Verify docker-compose.yml

Your docker-compose.yml should look like this (which it already does):
```yaml
services:
  app:
    image: ${ECR_REGISTRY}:${IMAGE_TAG}
    container_name: inception-app
    ports:
      - "8000:8000"
    env_file:
      - ./.env
    volumes:
      - ./storage:/app/storage
      - ./app/logs:/app/app/logs
    restart: unless-stopped
```

**Note:** DB credentials come from Secrets Manager at runtime, so no DB connection details needed in compose file.

#### 10. Update Environment Variables (if needed)

Make sure `.env` has:
```bash
# ECR Image
ECR_REGISTRY=421730342685.dkr.ecr.eu-north-1.amazonaws.com/inception-app
IMAGE_TAG=latest

# Database connection details (for Secrets Manager fallback)
DB_HOST=inception-db.cp68u8qqac8g.eu-north-1.rds.amazonaws.com
DB_PORT=5432
DB_NAME=inception-db
DB_SSLMODE=require

# Secrets Manager (optional - defaults to rds!db-497957fc-371a-40e2-aa21-7fab6082e1e1)
DB_SECRET_NAME=rds!db-497957fc-371a-40e2-aa21-7fab6082e1e1
AWS_REGION=eu-north-1

# Chunked generation
CEA_USE_CHUNKED_GENERATION=true

# Other app configs (Cognito, Ollama, Grok, etc.)
# ... your existing env vars
```

**Note:** DB username/password come from Secrets Manager automatically - don't put them in .env!

#### 11. Run Database Migration (ONE-TIME ONLY - if source_type column doesn't exist)

**Option A:** Run from EC2 host (if psql installed):
```bash
psql -h inception-db.cp68u8qqac8g.eu-north-1.rds.amazonaws.com \
     -U postgres \
     -d inception-db \
     --set=sslmode=require \
     -f migrations/002_add_source_type_column.sql
```

**Option B:** Run from inside container (migrations are in the image):
```bash
docker run --rm \
  -v $(pwd)/migrations:/migrations \
  421730342685.dkr.ecr.eu-north-1.amazonaws.com/inception-app:latest \
  psql -h inception-db.cp68u8qqac8g.eu-north-1.rds.amazonaws.com \
       -U postgres \
       -d inception-db \
       --set=sslmode=require \
       -f /migrations/002_add_source_type_column.sql
```

**Note:** Only run this ONCE. After that, skip this step for future deployments.

#### 12. Deploy (Your Normal Workflow)
```bash
docker compose down
docker compose up -d
```

#### 13. Check Logs
```bash
docker compose logs -f inception-app
```

**Look for:**
- ✅ "Secrets fetched from Secrets Manager"
- ✅ "Database connection pool initialized"
- ✅ "Core services warmed at startup"

---

## ✅ Verification

### Test Application
```bash
curl http://localhost:8000/healthz
```

### Test Chunked Generation
Send this in the chatbot:
```
"Create a blog post about mindfulness, an X post, and a Facebook ad"
```

**Expected:**
- Logs show: "Detected multi-part request with 3 chunks"
- Response has all 3 parts (no truncation)

### Check Database
```bash
# Connect to RDS
psql -h inception-db.cp68u8qqac8g.eu-north-1.rds.amazonaws.com \
     -U postgres \
     -d inception-db \
     --set=sslmode=require

# Verify source_type column exists
\d semantic_memory
```

---

## 🎯 Summary

**Yes, everything is ready!** 

**Deployment order:**
1. ✅ Build locally
2. ✅ Push to ECR
3. ✅ On EC2: Pull image, docker compose down/up (that's it!)

**Note:** Code is in the Docker image - no need to pull code from git!

**Key changes:**
- ✅ Chunked generation (fixes truncation)
- ✅ Secrets Manager integration
- ✅ source_type column migration

**Ready to deploy!** 🚀

