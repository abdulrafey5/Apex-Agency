# /data/inception/app/services/db_service.py
"""
Database service for PostgreSQL + pgvector integration.
Handles all database connections and provides high-level query methods.
"""

import os
import logging
import psycopg2
from psycopg2.extras import RealDictCursor, Json
from psycopg2.pool import ThreadedConnectionPool
from contextlib import contextmanager
from typing import List, Dict, Any, Optional, Tuple
from pathlib import Path
import json

# Load .env file BEFORE reading environment variables
try:
    from dotenv import load_dotenv
    app_dir = Path(__file__).resolve().parent.parent
    env_path = app_dir / ".env"
    if env_path.exists():
        load_dotenv(env_path)
except ImportError:
    # python-dotenv not installed, skip
    print("[DB_SERVICE] ❌ python-dotenv not installed, .env file will not be loaded")
except Exception as e:
    print(f"[DB_SERVICE] ❌ Failed to load .env file: {e}")


class DatabaseService:
    """PostgreSQL database service with connection pooling."""
    
    def __init__(self):
        self.db_host = os.getenv("DB_HOST", "localhost")
        self.db_port = int(os.getenv("DB_PORT", "5432"))
        self.db_name = os.getenv("DB_NAME", "inception")
        self.db_user = os.getenv("DB_USER", "postgres")
        self.db_password = os.getenv("DB_PASSWORD", "")
        # SSL mode: disable, allow, prefer, require, verify-ca, verify-full
        self.ssl_mode = os.getenv("DB_SSLMODE", "prefer")
        
        # Debug output - will show in logs
        print(f"[DB_SERVICE] Connecting to: host={self.db_host}, port={self.db_port}, db={self.db_name}, user={self.db_user}, sslmode={self.ssl_mode}")
        logging.info(f"DatabaseService initializing: host={self.db_host}, port={self.db_port}, db={self.db_name}, user={self.db_user}, sslmode={self.ssl_mode}")
        
        self.pool = None
        self._init_pool()
    
    def _init_pool(self):
        """Initialize connection pool."""
        try:
            # Build connection parameters
            conn_params = {
                "host": self.db_host,
                "port": self.db_port,
                "database": self.db_name,
                "user": self.db_user,
                "password": self.db_password,
                "sslmode": self.ssl_mode
            }
            
            self.pool = ThreadedConnectionPool(
                minconn=1,
                maxconn=10,
                **conn_params
            )
            logging.info(f"Database connection pool initialized: {self.db_name}@{self.db_host}")
        except Exception as e:
            logging.error(f"Failed to initialize database pool: {e}")
            self.pool = None
    
    @contextmanager
    def get_connection(self):
        """Get a database connection from the pool."""
        if not self.pool:
            raise RuntimeError("Database pool not initialized")
        
        conn = self.pool.getconn()
        try:
            yield conn
            conn.commit()
        except Exception as e:
            conn.rollback()
            raise
        finally:
            self.pool.putconn(conn)
    
    def execute_query(self, query: str, params: tuple = None) -> List[Dict[str, Any]]:
        """Execute a SELECT query and return results as list of dicts."""
        with self.get_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(query, params)
                return [dict(row) for row in cur.fetchall()]
    
    def execute_update(self, query: str, params: tuple = None) -> int:
        """Execute an INSERT/UPDATE/DELETE query and return affected rows."""
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query, params)
                return cur.rowcount
    
    def execute_one(self, query: str, params: tuple = None) -> Optional[Dict[str, Any]]:
        """Execute a query and return a single row."""
        results = self.execute_query(query, params)
        return results[0] if results else None
    
    # ============================================================================
    # Agent Messages (Chat History)
    # ============================================================================
    
    def save_message(
        self,
        thread_id: str,
        role: str,
        message_text: str,
        user_id: Optional[str] = None,
        agent_id: str = "cea",
        metadata: Optional[Dict[str, Any]] = None
    ) -> int:
        """Save a message to agent_messages table."""
        query = """
            INSERT INTO agent_messages (thread_id, role, message_text, user_id, agent_id, metadata)
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING id
        """
        metadata_json = Json(metadata) if metadata else Json({})
        result = self.execute_one(query, (thread_id, role, message_text, user_id, agent_id, metadata_json))
        return result["id"] if result else None
    
    def get_thread_messages(
        self,
        thread_id: str,
        limit: int = 20,
        offset: int = 0
    ) -> List[Dict[str, Any]]:
        """Get messages for a thread, ordered by created_at."""
        query = """
            SELECT id, role, message_text, metadata, created_at
            FROM agent_messages
            WHERE thread_id = %s
            ORDER BY created_at ASC
            LIMIT %s OFFSET %s
        """
        return self.execute_query(query, (thread_id, limit, offset))
    
    def get_recent_messages(
        self,
        thread_id: str,
        count: int = 6
    ) -> List[Dict[str, Any]]:
        """Get the most recent N messages for a thread."""
        query = """
            SELECT id, role, message_text, metadata, created_at
            FROM agent_messages
            WHERE thread_id = %s
            ORDER BY created_at DESC
            LIMIT %s
        """
        results = self.execute_query(query, (thread_id, count))
        return list(reversed(results))  # Return in chronological order
    
    # ============================================================================
    # Semantic Memory (RAG / Knowledge Base)
    # ============================================================================
    
    def upsert_semantic_memory(
        self,
        content: str,
        embedding: List[float],
        metadata: Optional[Dict[str, Any]] = None,
        source_type: str = "manual",
        source_id: Optional[str] = None
    ) -> int:
        """Upsert a semantic memory entry with embedding."""
        # Convert embedding list to PostgreSQL vector format: '[0.1,0.2,...]'
        embedding_str = '[' + ','.join(map(str, embedding)) + ']'
        
        # Check if entry exists (by source_id if provided)
        if source_id:
            existing = self.execute_one(
                "SELECT id FROM semantic_memory WHERE source_id = %s",
                (source_id,)
            )
            if existing:
                # Update existing
                query = """
                    UPDATE semantic_memory
                    SET content = %s, embedding = %s::vector, metadata = %s, updated_at = CURRENT_TIMESTAMP
                    WHERE source_id = %s
                    RETURNING id
                """
                result = self.execute_one(
                    query,
                    (content, embedding_str, Json(metadata) if metadata else Json({}), source_id)
                )
                return result["id"] if result else None
        
        # Insert new
        query = """
            INSERT INTO semantic_memory (content, embedding, metadata, source_type, source_id)
            VALUES (%s, %s::vector, %s, %s, %s)
            RETURNING id
        """
        result = self.execute_one(
            query,
            (content, embedding_str, Json(metadata) if metadata else Json({}), source_type, source_id)
        )
        return result["id"] if result else None
    
    def semantic_search(
        self,
        query_embedding: List[float],
        match_threshold: float = 0.7,
        match_count: int = 5,
        filter_metadata: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """Search semantic memory using vector similarity."""
        # Convert embedding list to PostgreSQL vector format
        embedding_str = '[' + ','.join(map(str, query_embedding)) + ']'
        query = """
            SELECT * FROM semantic_search(%s::vector, %s, %s, %s)
        """
        filter_json = Json(filter_metadata) if filter_metadata else None
        return self.execute_query(query, (embedding_str, match_threshold, match_count, filter_json))
    
    # ============================================================================
    # Episodic Memory
    # ============================================================================
    
    def save_episodic_memory(
        self,
        user_id: str,
        summary_text: str,
        embedding: Optional[List[float]] = None,
        memory_type: str = "preference",
        metadata: Optional[Dict[str, Any]] = None
    ) -> int:
        """Save episodic memory for a user."""
        query = """
            INSERT INTO agent_episodic_memory (user_id, summary_text, embedding, memory_type, metadata)
            VALUES (%s, %s, %s::vector, %s, %s)
            RETURNING id
        """
        embedding_str = '[' + ','.join(map(str, embedding)) + ']' if embedding else None
        result = self.execute_one(
            query,
            (user_id, summary_text, embedding_str, memory_type, Json(metadata) if metadata else Json({}))
        )
        return result["id"] if result else None
    
    def get_user_episodic_memories(
        self,
        user_id: str,
        memory_type: Optional[str] = None,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """Get episodic memories for a user."""
        if memory_type:
            query = """
                SELECT id, summary_text, metadata, memory_type, created_at
                FROM agent_episodic_memory
                WHERE user_id = %s AND memory_type = %s
                ORDER BY created_at DESC
                LIMIT %s
            """
            return self.execute_query(query, (user_id, memory_type, limit))
        else:
            query = """
                SELECT id, summary_text, metadata, memory_type, created_at
                FROM agent_episodic_memory
                WHERE user_id = %s
                ORDER BY created_at DESC
                LIMIT %s
            """
            return self.execute_query(query, (user_id, limit))
    
    # ============================================================================
    # Async Tasks
    # ============================================================================
    
    def save_task(
        self,
        task_id: str,
        task_type: str,
        status: str = "pending",
        user_id: Optional[str] = None,
        thread_id: Optional[str] = None,
        task_data: Optional[Dict[str, Any]] = None,
        result_data: Optional[Dict[str, Any]] = None,
        progress_log: Optional[List[Dict[str, Any]]] = None,
        agent_insights: Optional[Dict[str, Any]] = None,
        error_message: Optional[str] = None,
        duration_minutes: Optional[int] = None,
        completed_agents: int = 0
    ) -> bool:
        """Save or update an async task."""
        # Check if task exists
        existing = self.execute_one("SELECT id FROM async_tasks WHERE id = %s", (task_id,))
        
        if existing:
            # Update existing task
            query = """
                UPDATE async_tasks
                SET status = %s, task_data = %s, result_data = %s, progress_log = %s,
                    agent_insights = %s, error_message = %s, duration_minutes = %s,
                    completed_agents = %s, updated_at = CURRENT_TIMESTAMP,
                    completed_at = CASE WHEN %s IN ('completed', 'failed') THEN CURRENT_TIMESTAMP ELSE completed_at END
                WHERE id = %s
            """
            self.execute_update(
                query,
                (
                    status, Json(task_data) if task_data else Json({}),
                    Json(result_data) if result_data else Json({}),
                    Json(progress_log) if progress_log else Json([]),
                    Json(agent_insights) if agent_insights else Json({}),
                    error_message, duration_minutes, completed_agents, status, task_id
                )
            )
        else:
            # Insert new task
            query = """
                INSERT INTO async_tasks (
                    id, task_type, status, user_id, thread_id, task_data, result_data,
                    progress_log, agent_insights, error_message, duration_minutes, completed_agents
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """
            self.execute_update(
                query,
                (
                    task_id, task_type, status, user_id, thread_id,
                    Json(task_data) if task_data else Json({}),
                    Json(result_data) if result_data else Json({}),
                    Json(progress_log) if progress_log else Json([]),
                    Json(agent_insights) if agent_insights else Json({}),
                    error_message, duration_minutes, completed_agents
                )
            )
        return True
    
    def get_task(self, task_id: str) -> Optional[Dict[str, Any]]:
        """Get an async task by ID."""
        query = """
            SELECT * FROM async_tasks WHERE id = %s
        """
        return self.execute_one(query, (task_id,))


# Global database service instance
_db_service = None


def get_db_service() -> DatabaseService:
    """Get or create the global database service instance."""
    global _db_service
    if _db_service is None:
        _db_service = DatabaseService()
    return _db_service

