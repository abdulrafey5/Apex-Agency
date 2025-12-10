# Vectorization Setup Guide

## Overview

This document explains how to vectorize the Marketing Department document and set up RAG (Retrieval-Augmented Generation) for agent/role queries.

## What Was Changed

### 1. Simplified Agent System (`app/services/incubator_agents.py`)
   - **Removed**: 5 specialized hardcoded agents (Marketing Expert, Financial Advisor, etc.)
   - **Added**: General-purpose agent system that loads agent info from vectorized documents via RAG
   - Agents are now dynamically configured from documents, not hardcoded

### 2. Document Ingestion Service (`app/services/document_ingestion_service.py`)
   - Parses YAML-like department structures
   - Chunks documents intelligently (with sentence boundary detection)
   - Generates embeddings using OpenAI or Ollama
   - Stores in both:
     - **Cloudflare Vectorize** (external vector index)
     - **PostgreSQL + pgvector** (internal database)

### 3. RAG Service Updates (`app/services/rag_service.py`)
   - Added `query_agent_info()` function to query agent/role information
   - Returns formatted context for use in prompts

### 4. New API Routes (`app/routes/chat.py`)
   - `POST /vectorize/document` - Vectorize a document
   - `GET/POST /vectorize/query-agent` - Query for agent information

## How to Vectorize the Marketing Department Document

### Option 1: Using the Python Script (Recommended)

```bash
cd app
python scripts/vectorize_marketing_department.py
```

This will:
- Parse the Marketing Department YAML structure
- Chunk it into searchable pieces
- Generate embeddings
- Store in both Vectorize and PostgreSQL

### Option 2: Using the API Endpoint

```bash
curl -X POST http://localhost:3000/vectorize/document \
  -H "Content-Type: application/json" \
  -d '{
    "document_text": "<paste Marketing Department YAML here>",
    "document_id": "marketing_department_v1",
    "document_type": "agent_library",
    "metadata": {
      "department": "Marketing Department",
      "version": "1.0"
    },
    "parse_structure": true
  }'
```

## Testing Agent Queries

### Test via API

```bash
# Query: "who is Sophie?"
curl "http://localhost:3000/vectorize/query-agent?query=who%20is%20Sophie"

# Query: "what does Colby do?"
curl -X POST http://localhost:3000/vectorize/query-agent \
  -H "Content-Type: application/json" \
  -d '{"query": "what does Colby do?", "top_k": 5}'
```

### Test via Chat

In the chat interface, try:
- "who is Sophie?"
- "what does Colby do?"
- "who is the Marketing Department manager?"
- "what are Sofie's responsibilities?"

The system should retrieve relevant information from the vectorized documents.

## How It Works

1. **Document Ingestion**:
   - Document is parsed (if structured) or chunked directly
   - Each chunk is embedded using OpenAI or Ollama
   - Chunks are stored with metadata (document_id, document_type, etc.)

2. **Query Process**:
   - User query is embedded
   - Vector similarity search finds relevant chunks
   - Results are formatted as context for the LLM

3. **Agent Lookup**:
   - When user references an agent (e.g., "have Sophie work on this"), the system:
     - Queries the vector store for "Sophie"
     - Retrieves her role, responsibilities, tools
     - Includes this context in the agent's prompt

## Next Steps

### 1. Test Vectorization
```bash
python app/scripts/vectorize_marketing_department.py
```

### 2. Test Queries
```bash
# Test via API or chat interface
curl "http://localhost:3000/vectorize/query-agent?query=who%20is%20Sophie"
```

### 3. Enable AI to Write Documents
The client wants the AI to be able to write documents back to the vector store. This will be implemented next:
- AI generates new agent profiles or SOPs
- Documents are automatically vectorized and stored
- Future queries can retrieve AI-generated content

## Configuration

Make sure these environment variables are set in `.env`:

```bash
# Database
DB_HOST=172.18.203.149
DB_PORT=5432
DB_NAME=inception
DB_USER=postgres
DB_PASSWORD=user123

# Embeddings (choose one)
OPENAI_API_KEY=your_key_here  # Recommended
# OR
OLLAMA_EMBEDDING_MODEL=nomic-embed-text  # Fallback

# Cloudflare Vectorize (optional)
CLOUDFLARE_API_KEY=your_key
CLOUDFLARE_ACCOUNT_ID=your_account_id
CLOUDFLARE_VECTORIZE_INDEX_NAME=product-index
```

## Troubleshooting

### "Failed to generate embedding"
- Check that `OPENAI_API_KEY` is set OR `OLLAMA_EMBEDDING_MODEL` is available
- Test embedding service: `python -c "from services.embedding_service import generate_embedding; print(generate_embedding('test'))"`

### "Database connection failed"
- Verify PostgreSQL is running and accessible
- Check `DB_HOST`, `DB_PORT`, `DB_USER`, `DB_PASSWORD` in `.env`
- Test connection: `psql -U postgres -h 172.18.203.149 -d inception`

### "No results from query"
- Ensure document was vectorized successfully
- Check that `document_type` matches in query filter
- Lower `match_threshold` in query (default 0.7, try 0.5)

