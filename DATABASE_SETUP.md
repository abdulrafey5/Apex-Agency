# Database Setup Guide - PostgreSQL + pgvector

This guide will help you set up PostgreSQL with pgvector extension for the Inception AI Agent system.

## Prerequisites

- PostgreSQL 12+ installed
- Access to create databases and extensions
- Python `psycopg2` package (will be installed via requirements)

## Step 1: Install PostgreSQL

### On Ubuntu/Debian:
```bash
sudo apt update
sudo apt install postgresql postgresql-contrib
```

### On macOS:
```bash
brew install postgresql
```

### On Windows:
Download from https://www.postgresql.org/download/windows/

## Step 2: Install pgvector Extension

### On Ubuntu/Debian:
```bash
sudo apt install postgresql-14-pgvector  # Adjust version number (12, 13, 14, 15, etc.)
```

### On macOS:
```bash
brew install pgvector
```

### On Windows:
Download from https://github.com/pgvector/pgvector/releases

### Manual Installation (if package manager doesn't work):
```bash
git clone --branch v0.5.1 https://github.com/pgvector/pgvector.git
cd pgvector
make
sudo make install
```

## Step 3: Create Database

```bash
# Connect to PostgreSQL
sudo -u postgres psql

# Create database
CREATE DATABASE inception;

# Connect to the new database
\c inception

# Enable pgvector extension
CREATE EXTENSION IF NOT EXISTS vector;

# Exit
\q
```

## Step 4: Run Schema Script

```bash
# From project root
psql -U postgres -d inception -f app/database/schema.sql
```

Or manually:
```bash
sudo -u postgres psql inception < app/database/schema.sql
```

## Step 5: Configure Environment Variables

Add to your `.env` file:

```env
# === PostgreSQL Database ===
DB_HOST=localhost
DB_PORT=5432
DB_NAME=inception
DB_USER=postgres
DB_PASSWORD=your_password_here

# === Embedding Model ===
# Option 1: Use OpenAI (recommended for production)
OPENAI_API_KEY=your_openai_api_key

# Option 2: Use local Ollama embedding model
OLLAMA_EMBEDDING_MODEL=nomic-embed-text
```

## Step 6: Install Python Dependencies

```bash
pip install psycopg2-binary
# or if you need full psycopg2:
pip install psycopg2
```

## Step 7: Test Database Connection

Run this Python script to test:

```python
from services.db_service import get_db_service

db = get_db_service()
print("Database connection successful!")
```

## Step 8: Migrate Existing Data (Optional)

If you have existing JSON files with chat history or tasks, run the migration script:

```bash
python app/database/migrate_from_files.py
```

## Verification

Check that tables were created:

```bash
psql -U postgres -d inception -c "\dt"
```

You should see:
- agent_messages
- semantic_memory
- agent_episodic_memory
- async_tasks
- agent_configs

## Troubleshooting

### "Extension vector does not exist"
- Make sure pgvector is installed: `sudo apt install postgresql-XX-pgvector`
- Check PostgreSQL version: `psql --version`
- Verify extension is available: `psql -U postgres -c "SELECT * FROM pg_available_extensions WHERE name = 'vector';"`

### "Connection refused"
- Check PostgreSQL is running: `sudo systemctl status postgresql`
- Verify connection settings in `.env`
- Check firewall rules

### "Permission denied"
- Ensure database user has CREATE and USAGE privileges
- Grant permissions: `GRANT ALL PRIVILEGES ON DATABASE inception TO postgres;`

## Next Steps

1. The system will automatically use the database once configured
2. Existing file-based storage will continue to work as fallback
3. New data will be stored in the database
4. Use RAG queries via `rag_service.py` for semantic search

