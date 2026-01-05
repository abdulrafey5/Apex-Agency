-- ============================================================================
-- SQL Queries to Check RDS Database Data
-- ============================================================================
-- Run these queries on your RDS instance to inspect what data is stored
--
-- Connect to RDS:
-- psql -h inception-db.cp68u8qqac8g.eu-north-1.rds.amazonaws.com \
--      -U postgres \
--      -d inception-db \
--      --set=sslmode=require
--
-- ============================================================================

-- 1. Check table row counts
SELECT 
    'users' as table_name, 
    COUNT(*) as row_count 
FROM users
UNION ALL
SELECT 
    'chats' as table_name, 
    COUNT(*) as row_count 
FROM chats
UNION ALL
SELECT 
    'messages' as table_name, 
    COUNT(*) as row_count 
FROM messages
UNION ALL
SELECT 
    'semantic_memory' as table_name, 
    COUNT(*) as row_count 
FROM semantic_memory;

-- 2. View all users
SELECT user_id, name, email, created_at 
FROM users 
ORDER BY created_at DESC;

-- 3. View all chats (threads)
SELECT 
    c.chat_id,
    c.chat_title as thread_id,
    u.name as user_name,
    u.email,
    COUNT(m.message_id) as message_count,
    MAX(m.created_at) as last_message_at,
    c.created_at as chat_created_at
FROM chats c
LEFT JOIN users u ON c.user_id = u.user_id
LEFT JOIN messages m ON c.chat_id = m.chat_id
GROUP BY c.chat_id, c.chat_title, u.name, u.email, c.created_at
ORDER BY last_message_at DESC NULLS LAST;

-- 4. View recent messages (last 20)
SELECT 
    m.message_id,
    c.chat_title as thread_id,
    m.role,
    LEFT(m.content, 100) as content_preview,
    m.created_at
FROM messages m
JOIN chats c ON m.chat_id = c.chat_id
ORDER BY m.created_at DESC
LIMIT 20;

-- 5. View messages for a specific thread (replace 'shared_global_thread' with your thread_id)
SELECT 
    m.message_id,
    m.role,
    m.content,
    m.created_at
FROM messages m
JOIN chats c ON m.chat_id = c.chat_id
WHERE c.chat_title = 'shared_global_thread'
ORDER BY m.created_at ASC;

-- 6. Check semantic_memory entries (knowledge base)
SELECT 
    id,
    LEFT(content, 100) as content_preview,
    source_type,
    source_id,
    created_at
FROM semantic_memory
ORDER BY created_at DESC
LIMIT 20;

-- 7. Count semantic_memory by source_type
SELECT 
    source_type,
    COUNT(*) as count
FROM semantic_memory
GROUP BY source_type
ORDER BY count DESC;

-- 8. View full message content for a specific chat (replace chat_id)
-- SELECT 
--     m.message_id,
--     m.role,
--     m.content,
--     m.created_at
-- FROM messages m
-- WHERE m.chat_id = 1  -- Replace with actual chat_id
-- ORDER BY m.created_at ASC;

-- 9. Check for duplicate messages (should be empty if working correctly)
SELECT 
    chat_id,
    role,
    content,
    COUNT(*) as duplicate_count
FROM messages
GROUP BY chat_id, role, content
HAVING COUNT(*) > 1;

-- 10. Check message length distribution
SELECT 
    CASE 
        WHEN LENGTH(content) < 100 THEN '< 100 chars'
        WHEN LENGTH(content) < 500 THEN '100-500 chars'
        WHEN LENGTH(content) < 1000 THEN '500-1000 chars'
        WHEN LENGTH(content) < 5000 THEN '1000-5000 chars'
        ELSE '> 5000 chars'
    END as length_range,
    COUNT(*) as count
FROM messages
GROUP BY length_range
ORDER BY 
    CASE length_range
        WHEN '< 100 chars' THEN 1
        WHEN '100-500 chars' THEN 2
        WHEN '500-1000 chars' THEN 3
        WHEN '1000-5000 chars' THEN 4
        ELSE 5
    END;

-- 11. View semantic_memory with embeddings (check if embeddings are populated)
SELECT 
    id,
    LEFT(content, 50) as content_preview,
    source_type,
    array_length(string_to_array(embedding::text, ','), 1) as embedding_dimension,
    created_at
FROM semantic_memory
LIMIT 10;

-- 12. Check for recent activity (last 24 hours)
SELECT 
    'users' as table_name,
    COUNT(*) as recent_count
FROM users
WHERE created_at > NOW() - INTERVAL '24 hours'
UNION ALL
SELECT 
    'chats' as table_name,
    COUNT(*) as recent_count
FROM chats
WHERE created_at > NOW() - INTERVAL '24 hours'
UNION ALL
SELECT 
    'messages' as table_name,
    COUNT(*) as recent_count
FROM messages
WHERE created_at > NOW() - INTERVAL '24 hours'
UNION ALL
SELECT 
    'semantic_memory' as table_name,
    COUNT(*) as recent_count
FROM semantic_memory
WHERE created_at > NOW() - INTERVAL '24 hours';

