# Data Collection Guide

## How Your Database Gets Populated

Your database is populated **automatically** when users interact with the chatbot. Here's how it works:

### 1. **Chat Messages** (`users`, `chats`, `messages` tables)

**When:** Every time a user sends a message in the chatbot

**What happens:**
1. User sends a message → Stored in `messages` table
2. CEA generates a response → Stored in `messages` table
3. Each conversation thread is mapped to a `chat` record
4. User info is stored in `users` table (or uses default "anon@local" user)

**Flow:**
```
User Message → /chat endpoint → delegate_cea_task() → Response
     ↓                                                      ↓
save_thread() → db.replace_thread_messages() → messages table
```

**To populate:** Just use the chatbot! Every conversation automatically saves to the database.

### 2. **Semantic Memory** (`semantic_memory` table)

**When:** 
- Initial seeding (via `seed_kb.py`)
- When agents interact and create knowledge (future feature)

**What happens:**
1. Documents are chunked and embedded
2. Each chunk is stored in `semantic_memory` with its vector embedding
3. Used for RAG (Retrieval-Augmented Generation)

**To populate:**
```bash
# Run the seeding script (populates agent library and SOPs)
python app/scripts/seed_kb.py
```

**Current content:**
- Agent library (Marketing, Sales, Product, etc.)
- SOPs (Standard Operating Procedures)
- Stage 0-4 workflows

### 3. **Agent Interactions** (Future - `agent_messages`, `agent_episodic_memory`)

**When:** When multi-agent orchestration runs (via `autogen_coordinator`)

**What happens:**
- Agent-to-agent messages stored in `agent_messages`
- Agent memories stored in `agent_episodic_memory`
- Agent configurations in `agent_configs`

**To populate:** This happens automatically when complex tasks trigger multi-agent workflows.

---

## How to Check Your Database

### Quick Check (Row Counts)

```sql
SELECT 'users' as table_name, COUNT(*) FROM users
UNION ALL SELECT 'chats', COUNT(*) FROM chats
UNION ALL SELECT 'messages', COUNT(*) FROM messages
UNION ALL SELECT 'semantic_memory', COUNT(*) FROM semantic_memory;
```

### View Recent Messages

```sql
SELECT 
    m.message_id,
    c.chat_title as thread_id,
    m.role,
    LEFT(m.content, 100) as preview,
    m.created_at
FROM messages m
JOIN chats c ON m.chat_id = c.chat_id
ORDER BY m.created_at DESC
LIMIT 20;
```

### View All Chats/Threads

```sql
SELECT 
    c.chat_id,
    c.chat_title,
    COUNT(m.message_id) as message_count,
    MAX(m.created_at) as last_message
FROM chats c
LEFT JOIN messages m ON c.chat_id = m.chat_id
GROUP BY c.chat_id, c.chat_title
ORDER BY last_message DESC;
```

### Full SQL Queries

See `check_db_data.sql` for comprehensive queries to inspect your database.

---

## Current Status

✅ **Working:**
- Chat messages are saved automatically
- Users and chats are created automatically
- Semantic memory can be seeded manually

🔄 **In Progress:**
- Agent interactions (will populate automatically when orchestration runs)
- Knowledge base expansion (AI will build this over time)

---

## Troubleshooting Empty Tables

If tables are empty after using the chatbot:

1. **Check database connection:**
   ```bash
   docker compose logs inception-app | grep -i "database\|db_service"
   ```

2. **Verify messages are being saved:**
   ```sql
   SELECT COUNT(*) FROM messages;
   ```

3. **Check for errors:**
   ```bash
   docker compose logs inception-app | grep -i "error\|exception"
   ```

4. **Verify thread_id mapping:**
   - Check if `shared_global_thread` exists in `chats` table
   - Check if messages are linked to the correct `chat_id`

---

## Expected Data Flow

```
User → Chatbot → CEA Response
  ↓                ↓
messages table ← save_thread()
  ↓
chats table (thread mapping)
  ↓
users table (user info)
```

**All of this happens automatically** - you don't need to manually insert data!

