# /data/inception/app/services/db_service.py
"""
Database service for PostgreSQL + pgvector integration.
Handles all database connections and provides high-level query methods.

🔐 PRODUCTION PATTERN: Fetches credentials from AWS Secrets Manager at runtime.
This ensures password rotation works correctly and .env files don't override secrets.
"""

import os
import logging
import psycopg2
from psycopg2.extras import RealDictCursor, Json
from psycopg2.pool import ThreadedConnectionPool
from contextlib import contextmanager
from typing import List, Dict, Any, Optional, Tuple
import json
import boto3
from botocore.exceptions import ClientError, BotoCoreError


def fetch_db_secret(secret_name: Optional[str] = None, region_name: str = "eu-north-1") -> dict:
    """
    Fetch DB credentials from AWS Secrets Manager.
    Returns dict with keys: 'username', 'password', 'host', 'dbname'.
    
    This is called at runtime (not at app boot) to support password rotation.
    
    Args:
        secret_name: AWS Secrets Manager secret name/ARN. If None, reads from DB_SECRET_NAME env var.
        region_name: AWS region for Secrets Manager.
    """
    if secret_name is None:
        secret_name = os.getenv("DB_SECRET_NAME", "rds!db-497957fc-371a-40e2-aa21-7fab6082e1e1")
    
    try:
        client = boto3.client("secretsmanager", region_name=region_name)
        response = client.get_secret_value(SecretId=secret_name)
        secret = json.loads(response["SecretString"])
        logging.info(f"[DB_SERVICE] ✅ Secrets fetched from Secrets Manager: {secret_name}")
        return secret
    except ClientError as e:
        error_code = e.response.get("Error", {}).get("Code", "Unknown")
        if error_code == "ResourceNotFoundException":
            logging.warning(f"[DB_SERVICE] ⚠️ Secret '{secret_name}' not found in Secrets Manager. Falling back to environment variables.")
        else:
            logging.error(f"[DB_SERVICE] ❌ AWS Secrets Manager error: {e}")
        raise
    except (BotoCoreError, json.JSONDecodeError, KeyError) as e:
        logging.error(f"[DB_SERVICE] ❌ Failed to parse secret: {e}")
        raise
    except Exception as e:
        logging.error(f"[DB_SERVICE] ❌ Unexpected error fetching secret: {e}")
        raise


class DatabaseService:
    """
    PostgreSQL database service with connection pooling.
    
    🔐 PRODUCTION: Fetches credentials from AWS Secrets Manager on initialization.
    Falls back to environment variables if Secrets Manager is unavailable.
    """
    
    def __init__(self, secret_name: Optional[str] = None, region_name: str = "eu-north-1"):
        """
        Initialize database service.
        
        Args:
            secret_name: AWS Secrets Manager secret name/ARN. If None, reads from DB_SECRET_NAME env var.
            region_name: AWS region for Secrets Manager.
        """
        # Get secret name from parameter or environment variable
        if secret_name is None:
            secret_name = os.getenv("DB_SECRET_NAME", "rds!db-497957fc-371a-40e2-aa21-7fab6082e1e1")
        
        # Try Secrets Manager first (production)
        try:
            secret = fetch_db_secret(secret_name, region_name)
            
            # Debug: Log secret keys to understand structure (without sensitive values)
            secret_keys = list(secret.keys())
            logging.info(f"[DB_SERVICE] Secret keys found: {secret_keys}")
            
            # RDS-managed secrets are read-only and may not include all fields
            # Strategy: Get credentials from secret, connection details from env vars (hybrid approach)
            
            # Username and password from Secrets Manager (sensitive data)
            self.db_user = (
                secret.get("username") or 
                secret.get("user") or 
                secret.get("masterUsername") or
                os.getenv("DB_USER", "postgres")
            )
            
            self.db_password = secret.get("password") or secret.get("masterPassword") or ""
            
            # Connection details: Try secret first, then fall back to environment variables
            # RDS secrets may include: host, port, dbname, engine, dbInstanceIdentifier
            self.db_host = (
                secret.get("host") or 
                secret.get("hostname") or 
                secret.get("address") or
                os.getenv("DB_HOST")  # No default - must be set in env if not in secret
            )
            
            if not self.db_host:
                raise ValueError("DB_HOST not found in secret and DB_HOST environment variable not set")
            
            port_value = secret.get("port") or secret.get("dbPort") or os.getenv("DB_PORT", "5432")
            self.db_port = int(port_value) if isinstance(port_value, (int, str)) and str(port_value).isdigit() else 5432
            
            self.db_name = (
                secret.get("dbname") or 
                secret.get("database") or 
                secret.get("dbInstanceIdentifier") or
                os.getenv("DB_NAME")  # No default - must be set in env if not in secret
            )
            
            if not self.db_name:
                raise ValueError("DB_NAME not found in secret and DB_NAME environment variable not set")
            
            # SSL mode: RDS secrets typically don't include this, use env var
            self.ssl_mode = secret.get("sslmode") or os.getenv("DB_SSLMODE", "require")
            
            self._credentials_source = "secrets_manager"
            logging.info(f"[DB_SERVICE] Using credentials from Secrets Manager: {secret_name}")
            logging.info(f"[DB_SERVICE] Parsed values - host: {self.db_host}, port: {self.db_port}, db: {self.db_name}, user: {self.db_user}, sslmode: {self.ssl_mode}")
        except Exception as e:
            # Fallback to environment variables (development/local)
            logging.warning(f"[DB_SERVICE] ⚠️ Secrets Manager unavailable, falling back to environment variables: {e}")
            self.db_host = os.getenv("DB_HOST", "localhost")
            self.db_port = int(os.getenv("DB_PORT", "5432"))
            self.db_name = os.getenv("DB_NAME", "inception")
            self.db_user = os.getenv("DB_USER", "postgres")
            self.db_password = os.getenv("DB_PASSWORD", "")
            self.ssl_mode = os.getenv("DB_SSLMODE", "prefer")
            self._credentials_source = "environment"
            logging.info(f"[DB_SERVICE] Using credentials from environment variables")
        
        # Store secret info for rotation-aware recreation
        self._secret_name = secret_name
        self._region_name = region_name
        
        # Debug output
        print(f"[DB_SERVICE] Connecting to: host={self.db_host}, port={self.db_port}, db={self.db_name}, user={self.db_user}, sslmode={self.ssl_mode} (source: {self._credentials_source})")
        logging.info(f"DatabaseService initializing: host={self.db_host}, port={self.db_port}, db={self.db_name}, user={self.db_user}, sslmode={self.ssl_mode}")
        
        self.pool = None
        self._init_pool()
    
    def _init_pool(self):
        """Initialize connection pool with current credentials."""
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
        except psycopg2.OperationalError as e:
            error_str = str(e).lower()
            if "password authentication failed" in error_str or "authentication failed" in error_str:
                # Password may have rotated - clear pool to force recreation
                self.pool = None
                error_msg = f"Database authentication failed - credentials may have rotated. Pool cleared. Error: {e}"
                logging.error(error_msg)
                print(f"[DB_SERVICE] ERROR: {error_msg}")
                print(f"[DB_SERVICE] 💡 If using Secrets Manager, restart the application to fetch new credentials.")
                raise RuntimeError("DB credentials rotated — restart pool or restart application")
            else:
                error_msg = f"Failed to initialize database pool: {e}"
                logging.error(error_msg)
                print(f"[DB_SERVICE] ERROR: {error_msg}")
                print(f"[DB_SERVICE] Check: DB_HOST={self.db_host}, DB_PORT={self.db_port}, DB_NAME={self.db_name}, DB_USER={self.db_user}")
                self.pool = None
                raise
        except Exception as e:
            error_msg = f"Failed to initialize database pool: {e}"
            logging.error(error_msg)
            print(f"[DB_SERVICE] ERROR: {error_msg}")
            print(f"[DB_SERVICE] Check: DB_HOST={self.db_host}, DB_PORT={self.db_port}, DB_NAME={self.db_name}, DB_USER={self.db_user}")
            self.pool = None
            raise
    
    @contextmanager
    def get_connection(self):
        """
        Get a database connection from the pool.
        
        Handles authentication failures by detecting password rotation.
        """
        if not self.pool:
            raise RuntimeError("Database pool not initialized")
        
        conn = self.pool.getconn()
        try:
            yield conn
            conn.commit()
        except psycopg2.OperationalError as e:
            conn.rollback()
            error_str = str(e).lower()
            if "password authentication failed" in error_str or "authentication failed" in error_str:
                # Credentials rotated - clear pool
                logging.error(f"[DB_SERVICE] Authentication failed during connection use - credentials may have rotated: {e}")
                self.pool = None
                raise RuntimeError("DB credentials rotated — restart application to fetch new credentials")
            raise
        except Exception as e:
            conn.rollback()
            raise
        finally:
            if self.pool:  # Only put back if pool still exists
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
    
    # -------------------------------------------------------------------------
    # Helpers for chats/messages schema (users, chats, messages)
    # -------------------------------------------------------------------------
    def _ensure_default_user(self) -> int:
        """
        Ensure a default user exists (for anon/shared threads).
        Returns user_id.
        """
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT user_id FROM users WHERE email = %s", ("anon@local",))
                row = cur.fetchone()
                if row:
                    return row[0]
                cur.execute(
                    "INSERT INTO users (name, email, password) VALUES (%s, %s, %s) RETURNING user_id",
                    ("Anon", "anon@local", "placeholder")
                )
                return cur.fetchone()[0]

    def _ensure_chat(self, thread_id: str, user_id: Optional[int] = None) -> int:
        """
        Map thread_id -> chat_id using chats table. Creates a chat if missing.
        """
        uid = user_id or self._ensure_default_user()
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT chat_id FROM chats WHERE chat_title = %s", (thread_id,))
                row = cur.fetchone()
                if row:
                    return row[0]
                cur.execute(
                    "INSERT INTO chats (user_id, chat_title) VALUES (%s, %s) RETURNING chat_id",
                    (uid, thread_id)
                )
                return cur.fetchone()[0]
    
    def get_thread_messages(
        self,
        thread_id: str,
        limit: int = 20,
        offset: int = 0
    ) -> List[Dict[str, Any]]:
        """Get messages for a thread (mapped to chats/messages), ordered by created_at."""
        chat_id = self._ensure_chat(thread_id)
        query = """
            SELECT message_id AS id, role, content AS message_text, created_at
            FROM messages
            WHERE chat_id = %s
            ORDER BY created_at ASC
            LIMIT %s OFFSET %s
        """
        return self.execute_query(query, (chat_id, limit, offset))
    
    def get_recent_messages(
        self,
        thread_id: str,
        count: int = 6
    ) -> List[Dict[str, Any]]:
        """Get the most recent N messages for a thread."""
        chat_id = self._ensure_chat(thread_id)
        query = """
            SELECT message_id AS id, role, content AS message_text, created_at
            FROM messages
            WHERE chat_id = %s
            ORDER BY created_at DESC
            LIMIT %s
        """
        results = self.execute_query(query, (chat_id, count))
        return list(reversed(results))  # chronological
    
    def replace_thread_messages(
        self,
        thread_id: str,
        messages: List[Dict[str, Any]],
        user_id: Optional[int] = None
    ) -> int:
        """
        Replace all messages for a thread (keeps order as provided) using messages table.
        Creates a chat for the thread if needed.
        """
        chat_id = self._ensure_chat(thread_id, user_id)
        total = 0
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM messages WHERE chat_id = %s", (chat_id,))
                for msg in messages:
                    role = msg.get("role", "assistant")
                    text = msg.get("content") or msg.get("message_text") or ""
                    cur.execute(
                        """
                        INSERT INTO messages (chat_id, role, content)
                        VALUES (%s, %s, %s)
                        """,
                        (chat_id, role, text)
                    )
                    total += 1
        return total
    
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

