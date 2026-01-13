# /data/inception/app/services/rag_service.py
"""
RAG (Retrieval-Augmented Generation) service for querying semantic memory.
Integrates with database semantic_memory table and embedding generation.
Also supports querying agent/role information from vectorized documents.
"""

import logging
from typing import List, Dict, Any, Optional
from services.db_service import get_db_service
from services.embedding_service import generate_embedding
from services.document_ingestion_service import get_ingestion_service


def query_semantic_memory(
    query_text: str,
    top_k: int = 5,
    match_threshold: float = 0.7,
    filter_metadata: Optional[Dict[str, Any]] = None
) -> List[Dict[str, Any]]:
    """
    Query semantic memory using RAG (vector similarity search).

    Args:
        query_text: Natural language query
        top_k: Number of results to return
        match_threshold: Minimum similarity score (0-1)
        filter_metadata: Optional metadata filter (e.g., {"source_type": "business_plan"})

    Returns:
        List of matching semantic memory entries with similarity scores
    """
    try:
        # Generate embedding for query
        query_embedding = generate_embedding(query_text)
        if not query_embedding:
            logging.warning(f"Failed to generate embedding for query: {query_text}")
            return []

        # Query database (lazy initialization - don't call at module level)
        db = get_db_service()
        results = db.semantic_search(
            query_embedding=query_embedding,
            match_threshold=match_threshold,
            match_count=top_k,
            filter_metadata=filter_metadata
        )

        logging.info(f"RAG query returned {len(results)} results for: {query_text[:50]}...")
        return results

    except Exception as e:
        logging.exception(f"RAG query failed: {e}")
        return []


def index_content(
    content: str,
    metadata: Optional[Dict[str, Any]] = None,
    source_type: str = "manual",
    source_id: Optional[str] = None
) -> Optional[int]:
    """
    Index content into semantic memory (generate embedding and store).

    Args:
        content: Text content to index
        metadata: Optional metadata dict
        source_type: Type of source (e.g., "agent_library", "sop", "manual")
        source_id: Unique identifier for the source

    Returns:
        ID of the inserted/updated semantic memory entry, or None on failure
    """
    try:
        # Generate embedding
        embedding = generate_embedding(content)
        if not embedding:
            logging.warning(f"Failed to generate embedding for content: {content[:50]}...")
            return None

        # Store in database (lazy initialization)
        db = get_db_service()
        memory_id = db.upsert_semantic_memory(
            content=content,
            embedding=embedding,
            metadata=metadata,
            source_type=source_type,
            source_id=source_id
        )

        logging.info(f"Indexed content into semantic memory: id={memory_id}, source_type={source_type}")
        return memory_id

    except Exception as e:
        logging.exception(f"Failed to index content: {e}")
        return None


def query_agent_info(query_text: str, top_k: int = 5) -> str:
    """
    Query for agent/role information and return formatted context string.

    Args:
        query_text: Natural language query about agents/roles
        top_k: Number of results to return

    Returns:
        Formatted string with agent information for use in prompts
    """
    try:
        results = query_semantic_memory(
            query_text=query_text,
            top_k=top_k,
            match_threshold=0.6,
            filter_metadata={"source_type": "agent_library"}
        )

        if not results:
            return ""

        formatted_parts = []
        for result in results:
            content = result.get("content", "")
            metadata = result.get("metadata", {})
            agent_name = metadata.get("agent_name", "Unknown")
            formatted_parts.append(f"{agent_name}: {content[:300]}")

        return "\n".join(formatted_parts)

    except Exception as e:
        logging.exception(f"Failed to query agent info: {e}")
        return ""


# Legacy class-based interface (for backward compatibility)
class RAGService:
    """RAG service to manage embeddings and semantic retrieval."""
    
    def __init__(self):
        # Lazy initialization - don't call get_db_service() at module level
        self.db = None
    
    def _get_db(self):
        """Lazy getter for database service."""
        if self.db is None:
            self.db = get_db_service()
        return self.db

    def upsert_embedding(self, chat_id: int, content: str, embedding: List[float], metadata: Optional[Dict[str, Any]] = None, source_id: Optional[str] = None) -> int:
        return self._get_db().upsert_semantic_memory(content, embedding, metadata, "manual", source_id)

    def get_chat_history(self, chat_id: int, limit: int = 50) -> List[Dict[str, Any]]:
        return self._get_db().get_chat_messages(chat_id, limit)

    def save_chat_message(self, chat_id: int, role: str, content: str) -> int:
        return self._get_db().save_message(chat_id, role, content)
