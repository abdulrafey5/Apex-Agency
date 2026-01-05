# Deployment Checklist - EC2 Deployment

## ✅ Pre-Deployment Checklist

### 1. Code Changes Summary
- ✅ Chunked generation service (handles multi-part requests)
- ✅ Database service (Secrets Manager integration)
- ✅ Migration updated (source_type column added)
- ✅ All files linted (no errors)

### 2. Files to Deploy
- ✅ `app/services/chunked_generation_service.py` (NEW)
- ✅ `app/services/cea_delegation_service.py` (UPDATED)
- ✅ `app/services/db_service.py` (UPDATED - Secrets Manager)
- ✅ `migrations/001_init_schema.sql` (UPDATED - source_type)
- ✅ `migrations/002_add_source_type_column.sql` (NEW - for existing DB)

### 3. Environment Variables (EC2)
Make sure your EC2 `.env` file has:
```bash
# ECR Image
ECR_REGISTRY=421730342685.dkr.ecr.eu-north-1.amazonaws.com/inception-app
IMAGE_TAG=latest

# Database connection details (for Secrets Manager fallback)
DB_HOST=inception-db.cp68u8qqac8g.eu-north-1.rds.amazonaws.com
DB_PORT=5432
DB_NAME=inception-db
DB_SSLMODE=require

# Secrets Manager (optional - code has default)
DB_SECRET_NAME=rds!db-497957fc-371a-40e2-aa21-7fab6082e1e1
AWS_REGION=eu-north-1

# Chunked generation (optional, defaults to true)
CEA_USE_CHUNKED_GENERATION=true

# Other app configs (Cognito, Ollama, Grok, etc.)
```

**Note:** DB username/password are fetched from Secrets Manager at runtime - don't put them in .env!

---

## 🚀 Deployment Steps

### Step 1: Build Docker Image Locally

```bash
# From project root
docker build -t inception-app:latest -f Dockerfile .
```

**Verify build:**
```bash
docker images | grep inception-app
```

### Step 2: Tag for ECR

```bash
# Tag the image for ECR
docker tag inception-app:latest \
  421730342685.dkr.ecr.eu-north-1.amazonaws.com/inception-app:latest
```

### Step 3: Login to ECR

```bash
# AWS CLI login to ECR
aws ecr get-login-password --region eu-north-1 | \
  docker login --username AWS --password-stdin \
  421730342685.dkr.ecr.eu-north-1.amazonaws.com
```

### Step 4: Push to ECR

```bash
# Push the image
docker push \
  421730342685.dkr.ecr.eu-north-1.amazonaws.com/inception-app:latest
```

**Verify push:**
```bash
aws ecr describe-images \
  --repository-name inception-app \
  --region eu-north-1
```

### Step 5: On EC2 - Pull and Deploy

**SSH into EC2:**
```bash
ssh ubuntu@your-ec2-ip
```

**Navigate to project:**
```bash
cd /opt/inception  # or wherever your project is
```

**Pull latest code:**
```bash
git pull origin main  # or your branch
```

**Update docker-compose.yml** (if needed):
- Make sure it uses ECR image instead of local build
- Update environment variables for RDS

**Login to ECR on EC2:**
```bash
aws ecr get-login-password --region eu-north-1 | \
  docker login --username AWS --password-stdin \
  421730342685.dkr.ecr.eu-north-1.amazonaws.com
```

**Pull latest image:**
```bash
docker pull \
  421730342685.dkr.ecr.eu-north-1.amazonaws.com/inception-app:latest
```

**Stop current containers:**
```bash
docker compose down
```

**Run database migration** (if source_type column is missing):
```bash
# Connect to RDS and run migration
psql -h inception-db.cp68u8qqac8g.eu-north-1.rds.amazonaws.com \
     -U postgres \
     -d inception-db \
     --set=sslmode=require \
     -f migrations/002_add_source_type_column.sql
```

**Start containers:**
```bash
docker compose up -d
```

**Check logs:**
```bash
docker compose logs -f inception-app
```

---

## 🔍 Post-Deployment Verification

### 1. Check Application Health

```bash
# On EC2
curl http://localhost:8000/healthz
```

### 2. Check Database Connection

```bash
# Check logs for successful DB connection
docker compose logs inception-app | grep -i "database\|db_service"

# Should see:
# ✅ Secrets fetched from Secrets Manager
# ✅ Database connection pool initialized
```

### 3. Test Chunked Generation

Send a multi-part request:
```
"Create a blog post about mindfulness, an X post, and a Facebook ad"
```

**Expected:**
- Logs show: "Detected multi-part request with 3 chunks"
- Response contains all 3 parts (blog, X, Facebook)
- No truncation or duplication

### 4. Verify Database Tables

```bash
# Connect to RDS
psql -h inception-db.cp68u8qqac8g.eu-north-1.rds.amazonaws.com \
     -U postgres \
     -d inception-db \
     --set=sslmode=require

# Check source_type column exists
\d semantic_memory

# Should show source_type column
```

---

## 🐛 Troubleshooting

### Issue: "column source_type does not exist"

**Fix:**
```bash
# Run migration
psql -h inception-db.cp68u8qqac8g.eu-north-1.rds.amazonaws.com \
     -U postgres \
     -d inception-db \
     --set=sslmode=require \
     -f migrations/002_add_source_type_column.sql
```

### Issue: "Database pool not initialized"

**Check:**
1. Secrets Manager credentials are correct
2. IAM role has Secrets Manager permissions
3. DB_HOST, DB_PORT, DB_NAME are set correctly in environment

### Issue: "Chunked generation not working"

**Check:**
1. Environment variable: `CEA_USE_CHUNKED_GENERATION=true`
2. Logs show: "Detected multi-part request"
3. Request actually has multiple parts (blog + X + Facebook, etc.)

---

## 📝 Quick Reference

### Docker Commands
```bash
# Build
docker build -t inception-app:latest -f Dockerfile .

# Tag
docker tag inception-app:latest \
  421730342685.dkr.ecr.eu-north-1.amazonaws.com/inception-app:latest

# Push
docker push \
  421730342685.dkr.ecr.eu-north-1.amazonaws.com/inception-app:latest

# On EC2: Pull
docker pull \
  421730342685.dkr.ecr.eu-north-1.amazonaws.com/inception-app:latest

# On EC2: Deploy
docker compose down
docker compose up -d
```

### Database Migration
```bash
psql -h inception-db.cp68u8qqac8g.eu-north-1.rds.amazonaws.com \
     -U postgres \
     -d inception-db \
     --set=sslmode=require \
     -f migrations/002_add_source_type_column.sql
```

---

## ✅ Success Criteria

After deployment, you should see:

1. ✅ Application starts without errors
2. ✅ Database connection successful (Secrets Manager working)
3. ✅ Chunked generation works (multi-part requests)
4. ✅ No truncation in responses
5. ✅ Database has source_type column
6. ✅ Chat messages saving to database
7. ✅ Semantic memory queries working

---

## 🎯 Next Steps After Deployment

1. **Test chunked generation** with various multi-part requests
2. **Monitor logs** for any errors
3. **Check database** to verify data is being saved
4. **Run seed script** if semantic_memory is empty:
   ```bash
   docker compose exec inception-app python app/scripts/seed_kb.py
   ```

