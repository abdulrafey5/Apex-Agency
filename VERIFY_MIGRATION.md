# Verify Migration Success

Run this to confirm the `source_type` column exists:

```bash
psql -h inception-db.cp68u8qqac8g.eu-north-1.rds.amazonaws.com \
     -U postgres \
     -d inception-db \
     --set=sslmode=require \
     -c "\d semantic_memory"
```

Or check with a simple query:

```bash
psql -h inception-db.cp68u8qqac8g.eu-north-1.rds.amazonaws.com \
     -U postgres \
     -d inception-db \
     --set=sslmode=require \
     -c "SELECT column_name, data_type, column_default FROM information_schema.columns WHERE table_name = 'semantic_memory' AND column_name = 'source_type';"
```

You should see `source_type` listed with type `text` and default `'manual'`.

---

## Next Steps

1. ✅ Migration complete - `source_type` column added
2. Restart your app service to pick up any code changes:
   ```bash
   sudo systemctl restart inception-app
   sudo systemctl status inception-app
   ```
3. Seed the knowledge base (if not already done):
   ```bash
   docker run --rm \
     421730342685.dkr.ecr.eu-north-1.amazonaws.com/inception-app:latest \
     python /app/scripts/seed_kb.py
   ```



