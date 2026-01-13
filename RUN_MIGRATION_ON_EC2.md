# Run Migration on EC2 (Without Pulling Code)

## Option 1: Run SQL Directly (Easiest)

Since you don't have the migration file on EC2, just run the SQL directly:

```bash
psql -h inception-db.cp68u8qqac8g.eu-north-1.rds.amazonaws.com \
     -U postgres \
     -d inception-db \
     --set=sslmode=require
```

Then paste this SQL:

```sql
BEGIN;

-- Add source_type column if it doesn't exist
ALTER TABLE semantic_memory 
ADD COLUMN IF NOT EXISTS source_type TEXT DEFAULT 'manual';

-- Create index for faster filtering
CREATE INDEX IF NOT EXISTS idx_semantic_memory_source_type 
ON semantic_memory(source_type);

-- Update existing rows to have a default source_type if NULL
UPDATE semantic_memory 
SET source_type = 'manual' 
WHERE source_type IS NULL;

COMMIT;
```

Type `\q` to exit.

---

## Option 2: Extract Migration from Container

If you want to use the file from the container:

```bash
# Extract the migration file from the Docker image
docker run --rm \
  421730342685.dkr.ecr.eu-north-1.amazonaws.com/inception-app:latest \
  cat /app/migrations/002_add_source_type_column.sql > /tmp/migration.sql

# Then run it
psql -h inception-db.cp68u8qqac8g.eu-north-1.rds.amazonaws.com \
     -U postgres \
     -d inception-db \
     --set=sslmode=require \
     -f /tmp/migration.sql
```

---

## Option 3: Run from Inside Container

```bash
# Run psql from inside the container (migrations are in /app/migrations)
docker run --rm \
  -e PGPASSWORD='your-password-here' \
  421730342685.dkr.ecr.eu-north-1.amazonaws.com/inception-app:latest \
  psql -h inception-db.cp68u8qqac8g.eu-north-1.rds.amazonaws.com \
       -U postgres \
       -d inception-db \
       --set=sslmode=require \
       -f /app/migrations/002_add_source_type_column.sql
```

**But you'll need the password** - better to use Option 1 or get password from Secrets Manager.

---

## ✅ Recommended: Option 1 (Direct SQL)

Just connect and paste the SQL - it's the simplest!







