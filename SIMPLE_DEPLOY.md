# Simple Deployment Workflow

## ✅ Your Current Workflow is Perfect!

Since you're using ECR images, you **don't need to pull code**. The code is already in the Docker image.

---

## 🚀 Simple Deployment Steps

### **LOCAL (Your Machine)**

```bash
# 1. Build
docker build -t inception-app:latest -f Dockerfile .

# 2. Tag
docker tag inception-app:latest \
  421730342685.dkr.ecr.eu-north-1.amazonaws.com/inception-app:latest

# 3. Login to ECR
aws ecr get-login-password --region eu-north-1 | \
  docker login --username AWS --password-stdin \
  421730342685.dkr.ecr.eu-north-1.amazonaws.com

# 4. Push
docker push \
  421730342685.dkr.ecr.eu-north-1.amazonaws.com/inception-app:latest
```

---

### **EC2 SERVER**

```bash
# 1. SSH to EC2
ssh ubuntu@your-ec2-ip

# 2. Navigate to project
cd /opt/inception

# 3. Login to ECR
aws ecr get-login-password --region eu-north-1 | \
  docker login --username AWS --password-stdin \
  421730342685.dkr.ecr.eu-north-1.amazonaws.com

# 4. Pull latest image
docker pull \
  421730342685.dkr.ecr.eu-north-1.amazonaws.com/inception-app:latest

# 5. Deploy (your normal workflow)
docker compose down
docker compose up -d

# 6. Check logs
docker compose logs -f inception-app
```

**That's it!** 🎉

---

## ⚠️ One-Time Migration (Only if source_type column doesn't exist)

**Run this ONCE** if your database doesn't have the `source_type` column:

```bash
# Option 1: From EC2 host (if psql installed)
psql -h inception-db.cp68u8qqac8g.eu-north-1.rds.amazonaws.com \
     -U postgres \
     -d inception-db \
     --set=sslmode=require \
     -f migrations/002_add_source_type_column.sql

# Option 2: From inside container (migrations are in the image)
docker run --rm \
  -v $(pwd)/migrations:/migrations \
  421730342685.dkr.ecr.eu-north-1.amazonaws.com/inception-app:latest \
  psql -h inception-db.cp68u8qqac8g.eu-north-1.rds.amazonaws.com \
       -U postgres \
       -d inception-db \
       --set=sslmode=require \
       -f /migrations/002_add_source_type_column.sql
```

**After running once, skip this step forever!**

---

## ✅ Why You Don't Need to Pull Code

1. ✅ **Code is in Docker image** - Dockerfile copies `app/` and `migrations/`
2. ✅ **Migrations included** - `COPY migrations/ ./migrations/` in Dockerfile
3. ✅ **Everything in image** - All code, dependencies, migrations

**Your workflow is correct:**
- Build → Push to ECR → Pull image → Restart containers

**No git pull needed!** 🎯

---

## 🔍 Quick Verification

After `docker compose up -d`, check logs:

```bash
docker compose logs -f inception-app | grep -i "secrets\|database\|chunked"
```

Should see:
- ✅ "Secrets fetched from Secrets Manager"
- ✅ "Database connection pool initialized"
- ✅ "Chunked generation" (if multi-part request)

---

## 📝 Summary

**Normal deployment:**
1. Build locally → Push to ECR
2. On EC2: Pull image → `docker compose down` → `docker compose up -d`

**No code pulling needed!** Your workflow is perfect! ✅

