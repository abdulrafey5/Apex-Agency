-- =========================================================
-- Inception / ApexAgency Initial Database Migration
-- PostgreSQL + pgvector
-- =========================================================

BEGIN;

-- ---------------------------------------------------------
-- 1. Extensions
-- ---------------------------------------------------------
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS vector;

-- ---------------------------------------------------------
-- 2. Users Table
-- ---------------------------------------------------------
CREATE TABLE IF NOT EXISTS users (
    user_id       SERIAL PRIMARY KEY,
    name          TEXT NOT NULL,
    email         TEXT UNIQUE NOT NULL,
    password      TEXT NOT NULL,
    created_at    TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- ---------------------------------------------------------
-- 3. Chats Table
-- ---------------------------------------------------------
CREATE TABLE IF NOT EXISTS chats (
    chat_id       SERIAL PRIMARY KEY,
    user_id       INTEGER NOT NULL,
    chat_title    TEXT NOT NULL,
    created_at    TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_chats_user
        FOREIGN KEY (user_id)
        REFERENCES users(user_id)
        ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_chats_user_id
    ON chats(user_id);

-- ---------------------------------------------------------
-- 4. Messages Table
-- ---------------------------------------------------------
CREATE TABLE IF NOT EXISTS messages (
    message_id    SERIAL PRIMARY KEY,
    chat_id       INTEGER NOT NULL,
    role          TEXT NOT NULL CHECK (role IN ('user', 'assistant', 'system', 'agent')),
    content       TEXT NOT NULL,
    created_at    TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_messages_chat
        FOREIGN KEY (chat_id)
        REFERENCES chats(chat_id)
        ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_messages_chat_id
    ON messages(chat_id);

CREATE INDEX IF NOT EXISTS idx_messages_created_at
    ON messages(created_at);

-- ---------------------------------------------------------
-- 5. Semantic Memory (RAG / Vector Store)
-- ---------------------------------------------------------
-- NOTE:
-- - Dimension must match your embedding model
-- - nomic-embed-text = 768
-- - text-embedding-3-small = 1536
--
-- Change ONLY if you change embedding model
-- ---------------------------------------------------------

CREATE TABLE IF NOT EXISTS semantic_memory (
    id            SERIAL PRIMARY KEY,
    content       TEXT NOT NULL,
    embedding     VECTOR(768) NOT NULL,
    metadata      JSONB DEFAULT '{}'::jsonb,
    source_id     TEXT UNIQUE,
    created_at    TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at    TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Vector index for similarity search
CREATE INDEX IF NOT EXISTS idx_semantic_memory_embedding
    ON semantic_memory
    USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100);

CREATE INDEX IF NOT EXISTS idx_semantic_memory_metadata
    ON semantic_memory
    USING GIN (metadata);

-- ---------------------------------------------------------
-- 6. Trigger to auto-update updated_at
-- ---------------------------------------------------------
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ language 'plpgsql';

DROP TRIGGER IF EXISTS trg_semantic_memory_updated
ON semantic_memory;

CREATE TRIGGER trg_semantic_memory_updated
BEFORE UPDATE ON semantic_memory
FOR EACH ROW
EXECUTE FUNCTION update_updated_at_column();

COMMIT;
