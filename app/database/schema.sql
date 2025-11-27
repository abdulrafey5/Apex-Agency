-- PostgreSQL + pgvector Database Schema for Inception AI Agent System
-- Run this script to create the database and all required tables

-- Enable pgvector extension
CREATE EXTENSION IF NOT EXISTS vector;

-- ============================================================================
-- 1. Agent Messages (Short-term conversation memory)
-- ============================================================================
CREATE TABLE IF NOT EXISTS agent_messages (
    id SERIAL PRIMARY KEY,
    thread_id VARCHAR(255) NOT NULL,
    agent_id VARCHAR(100) DEFAULT 'cea',
    user_id VARCHAR(255),
    role VARCHAR(20) NOT NULL CHECK (role IN ('system', 'user', 'assistant', 'agent')),
    message_text TEXT NOT NULL,
    metadata JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_agent_messages_thread_id ON agent_messages (thread_id);
CREATE INDEX idx_agent_messages_user_id ON agent_messages (user_id);
CREATE INDEX idx_agent_messages_created_at ON agent_messages (created_at);
CREATE INDEX idx_agent_messages_thread_created ON agent_messages (thread_id, created_at);

-- ============================================================================
-- 2. Semantic Memory (Long-term knowledge base, RAG)
-- ============================================================================
CREATE TABLE IF NOT EXISTS semantic_memory (
    id SERIAL PRIMARY KEY,
    content TEXT NOT NULL,
    embedding vector(1536),  -- OpenAI text-embedding-3-small dimension (adjust if using different model)
    metadata JSONB DEFAULT '{}'::jsonb,
    source_type VARCHAR(50) DEFAULT 'manual',  -- 'manual', 'business_plan', 'product', 'document'
    source_id VARCHAR(255),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_semantic_memory_embedding ON semantic_memory USING hnsw (embedding vector_cosine_ops);
CREATE INDEX idx_semantic_memory_source ON semantic_memory (source_type, source_id);
CREATE INDEX idx_semantic_memory_created_at ON semantic_memory (created_at);

-- ============================================================================
-- 3. Agent Episodic Memory (User preferences, session summaries)
-- ============================================================================
CREATE TABLE IF NOT EXISTS agent_episodic_memory (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(255) NOT NULL,
    summary_text TEXT NOT NULL,
    embedding vector(1536),
    memory_type VARCHAR(50) DEFAULT 'preference',  -- 'preference', 'session_summary', 'user_context'
    metadata JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_episodic_memory_user_id ON agent_episodic_memory (user_id);
CREATE INDEX idx_episodic_memory_type ON agent_episodic_memory (memory_type);
CREATE INDEX idx_episodic_memory_embedding ON agent_episodic_memory USING hnsw (embedding vector_cosine_ops);
CREATE INDEX idx_episodic_memory_user_created ON agent_episodic_memory (user_id, created_at);

-- ============================================================================
-- 4. Async Tasks (Incubator sessions, chat tasks)
-- ============================================================================
CREATE TABLE IF NOT EXISTS async_tasks (
    id VARCHAR(255) PRIMARY KEY,
    task_type VARCHAR(50) NOT NULL,  -- 'chat', 'incubator'
    status VARCHAR(50) NOT NULL DEFAULT 'pending',  -- 'pending', 'processing', 'completed', 'failed'
    user_id VARCHAR(255),
    thread_id VARCHAR(255),
    
    -- Task-specific data stored as JSONB for flexibility
    task_data JSONB DEFAULT '{}'::jsonb,  -- Input data (e.g., business_idea, message)
    result_data JSONB DEFAULT '{}'::jsonb,  -- Output data (e.g., business_plan, response)
    
    -- Progress tracking
    progress_log JSONB DEFAULT '[]'::jsonb,
    agent_insights JSONB DEFAULT '{}'::jsonb,
    
    -- Metadata
    error_message TEXT,
    duration_minutes INTEGER,
    completed_agents INTEGER DEFAULT 0,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP WITH TIME ZONE
);

CREATE INDEX idx_async_tasks_status ON async_tasks (status);
CREATE INDEX idx_async_tasks_type ON async_tasks (task_type);
CREATE INDEX idx_async_tasks_user_id ON async_tasks (user_id);
CREATE INDEX idx_async_tasks_thread_id ON async_tasks (thread_id);
CREATE INDEX idx_async_tasks_created_at ON async_tasks (created_at);

-- ============================================================================
-- 5. Agent Configs (System configuration, agent profiles)
-- ============================================================================
CREATE TABLE IF NOT EXISTS agent_configs (
    id SERIAL PRIMARY KEY,
    config_key VARCHAR(255) UNIQUE NOT NULL,
    config_value JSONB NOT NULL,
    config_type VARCHAR(50) DEFAULT 'system',  -- 'system', 'agent_profile', 'user_preference'
    description TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_agent_configs_key ON agent_configs (config_key);
CREATE INDEX idx_agent_configs_type ON agent_configs (config_type);

-- ============================================================================
-- Helper Functions
-- ============================================================================

-- Function to update updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Triggers for updated_at
CREATE TRIGGER update_semantic_memory_updated_at BEFORE UPDATE ON semantic_memory
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_episodic_memory_updated_at BEFORE UPDATE ON agent_episodic_memory
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_async_tasks_updated_at BEFORE UPDATE ON async_tasks
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_agent_configs_updated_at BEFORE UPDATE ON agent_configs
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- ============================================================================
-- Vector Similarity Search Function
-- ============================================================================
CREATE OR REPLACE FUNCTION semantic_search(
    query_embedding vector(1536),
    match_threshold float DEFAULT 0.7,
    match_count int DEFAULT 5,
    filter_metadata jsonb DEFAULT NULL
)
RETURNS TABLE (
    id int,
    content text,
    metadata jsonb,
    similarity float
)
LANGUAGE plpgsql
AS $$
BEGIN
    RETURN QUERY
    SELECT
        semantic_memory.id,
        semantic_memory.content,
        semantic_memory.metadata,
        1 - (semantic_memory.embedding <=> query_embedding) as similarity
    FROM semantic_memory
    WHERE 
        (filter_metadata IS NULL OR semantic_memory.metadata @> filter_metadata)
        AND (1 - (semantic_memory.embedding <=> query_embedding)) >= match_threshold
    ORDER BY semantic_memory.embedding <=> query_embedding
    LIMIT match_count;
END;
$$;
