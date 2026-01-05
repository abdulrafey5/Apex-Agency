# Embeddings and Chunks Storage Guide

## 📊 Current Database Structure

### Table: `semantic_memory`

This is the **single table** that stores all embeddings, chunks, and metadata.

**Schema:**
```sql
CREATE TABLE semantic_memory (
    id            SERIAL PRIMARY KEY,
    content       TEXT NOT NULL,              -- The text chunk
    embedding     VECTOR(768) NOT NULL,      -- Vector embedding (768 dimensions for nomic-embed-text)
    metadata      JSONB DEFAULT '{}'::jsonb, -- Additional metadata (source info, tags, etc.)
    source_type   TEXT DEFAULT 'manual',     -- Type: 'agent_library', 'sop', 'document', 'manual', etc.
    source_id     TEXT UNIQUE,               -- Unique identifier for the source document/chunk
    created_at    TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at    TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
```

**Indexes:**
- Vector similarity index: `idx_semantic_memory_embedding` (IVFFlat for cosine similarity)
- Metadata index: `idx_semantic_memory_metadata` (GIN index for JSONB queries)

---

## 🗂️ How Chunks Are Stored

### Current Approach: **One Row Per Chunk**

Each chunk is stored as a **separate row** in `semantic_memory`:

```
Document: "Marketing Agent Guide"
├── Chunk 1 → Row 1: content="Marketing agent overview...", embedding=[...], source_id="marketing_agent_chunk_1"
├── Chunk 2 → Row 2: content="Marketing strategies...", embedding=[...], source_id="marketing_agent_chunk_2"
└── Chunk 3 → Row 3: content="Campaign management...", embedding=[...], source_id="marketing_agent_chunk_3"
```

**Benefits:**
- ✅ Simple structure
- ✅ Easy to query individual chunks
- ✅ Efficient vector search
- ✅ Metadata per chunk (useful for filtering)

**Example Row:**
```json
{
  "id": 1,
  "content": "The Marketing Agent (Maria) specializes in creating comprehensive marketing strategies...",
  "embedding": [0.123, -0.456, 0.789, ...],  // 768 dimensions
  "metadata": {
    "source": "agent_library",
    "agent_name": "Maria",
    "department": "Marketing",
    "chunk_index": 0
  },
  "source_type": "agent_library",
  "source_id": "marketing_agent_chunk_0",
  "created_at": "2026-01-05T10:00:00Z"
}
```

---

## 📍 Where Embeddings Are Stored

### 1. **Database: PostgreSQL + pgvector**
- **Table:** `semantic_memory`
- **Column:** `embedding` (VECTOR(768))
- **Format:** PostgreSQL vector type (optimized for similarity search)

### 2. **Embedding Model:**
- **Model:** `nomic-embed-text` (via Ollama)
- **Dimensions:** 768
- **Fallback:** OpenAI `text-embedding-3-small` (1536 dims) - **NOT CURRENTLY USED**

⚠️ **Important:** If you switch to OpenAI embeddings, you must:
1. Alter the table: `ALTER TABLE semantic_memory ALTER COLUMN embedding TYPE VECTOR(1536);`
2. Regenerate all embeddings

---

## 🔍 How Chunks Are Created

### Process Flow:

```
Document Text
    ↓
[DocumentIngestionService]
    ↓
1. Parse & Chunk (split into ~500-1000 char chunks)
    ↓
2. Generate Embeddings (via embedding_service.py)
    ↓
3. Store in semantic_memory (via db_service.upsert_semantic_memory)
    ↓
Each chunk → One row with:
- content (text chunk)
- embedding (vector)
- metadata (source info)
- source_type (category)
- source_id (unique identifier)
```

### Chunking Strategy:

**Current Implementation:**
- **Chunk Size:** ~500-1000 characters (configurable)
- **Overlap:** None (can be added if needed)
- **Method:** Simple text splitting by paragraphs/sentences

**Example from `seed_kb.py`:**
```python
# Document is split into chunks
chunks = split_into_chunks(document_text, chunk_size=800)

# Each chunk gets:
# - Unique source_id: "marketing_agent_chunk_0", "marketing_agent_chunk_1", etc.
# - Metadata: {"agent_name": "Maria", "department": "Marketing", "chunk_index": 0}
# - Embedding: Generated via embedding_service.generate_embedding()
# - Stored: db_service.upsert_semantic_memory()
```

---

## 📋 Source Types

Current `source_type` values:

| Source Type | Description | Example source_id |
|------------|-------------|------------------|
| `agent_library` | Agent documentation | `marketing_agent_chunk_0` |
| `sop` | Standard Operating Procedures | `idea_vetting_sop_chunk_0` |
| `document` | User-uploaded documents | `chat_123_chunk_0` |
| `manual` | Manually added content | `manual_entry_1` |
| `business_plan` | Generated business plans | `plan_abc123_chunk_0` |

---

## 🔎 Querying Chunks

### 1. **Vector Similarity Search** (RAG):

```python
# Find similar chunks
results = db_service.semantic_search(
    query_embedding=[0.123, -0.456, ...],
    match_threshold=0.7,
    match_count=5,
    filter_metadata={"source_type": "agent_library"}
)
```

### 2. **Metadata Filtering**:

```sql
-- Find all chunks from a specific source
SELECT * FROM semantic_memory 
WHERE metadata->>'agent_name' = 'Maria';

-- Find chunks by source_type
SELECT * FROM semantic_memory 
WHERE source_type = 'agent_library';
```

### 3. **Get All Chunks for a Document**:

```sql
-- All chunks from marketing agent guide
SELECT * FROM semantic_memory 
WHERE source_id LIKE 'marketing_agent_chunk_%'
ORDER BY source_id;
```

---

## ✅ Is This Structure Correct?

**Yes!** This is a **standard RAG pattern**:

1. ✅ **One table** (`semantic_memory`) stores everything
2. ✅ **One row per chunk** (efficient for vector search)
3. ✅ **Embeddings in same table** (PostgreSQL pgvector)
4. ✅ **Metadata in JSONB** (flexible filtering)
5. ✅ **source_type + source_id** (tracks origin)

**No need for separate tables** because:
- Chunks are small (one row each)
- Embeddings are stored efficiently (pgvector)
- Metadata provides all context needed
- Simple queries and maintenance

---

## 🔧 Migration Note

**If your database is missing `source_type` column:**

Run this migration:
```sql
ALTER TABLE semantic_memory 
ADD COLUMN IF NOT EXISTS source_type TEXT DEFAULT 'manual';

CREATE INDEX IF NOT EXISTS idx_semantic_memory_source_type 
ON semantic_memory(source_type);
```

Or use the updated `migrations/001_init_schema.sql` file.

---

## 📊 Current Data Structure Summary

```
semantic_memory table:
├── id (PK)
├── content (TEXT) ← The chunk text
├── embedding (VECTOR(768)) ← The vector embedding
├── metadata (JSONB) ← Additional info (agent_name, department, etc.)
├── source_type (TEXT) ← Category (agent_library, sop, document, etc.)
├── source_id (TEXT UNIQUE) ← Unique identifier (e.g., "marketing_agent_chunk_0")
├── created_at (TIMESTAMP)
└── updated_at (TIMESTAMP)
```

**This is the correct and efficient structure for RAG!** ✅

