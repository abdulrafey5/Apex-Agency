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

        # Query database
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
        metadata: Optional metadata (e.g., {"title": "...", "category": "..."})
        source_type: Type of source ('manual', 'business_plan', 'product', 'document')
        source_id: Unique identifier for the source

    Returns:
        ID of the inserted/updated semantic memory entry, or None if failed
    """
    try:
        # Generate embedding
        embedding = generate_embedding(content)
        if not embedding:
            logging.warning(f"Failed to generate embedding for content indexing")
            return None

        # Store in database
        db = get_db_service()
        memory_id = db.upsert_semantic_memory(
            content=content,
            embedding=embedding,
            metadata=metadata,
            source_type=source_type,
            source_id=source_id
        )

        logging.info(f"Indexed content into semantic memory (ID: {memory_id})")
        return memory_id

    except Exception as e:
        logging.exception(f"Failed to index content: {e}")
        return None


def query_agent_info(
    query: str,
    top_k: int = 5
) -> str:
    """
    Query for agent/role information using RAG.
    Returns formatted context string for use in prompts.

    Args:
        query: Natural language query (e.g., "who is Sophie?", "what does Colby do?")
        top_k: Number of results to return

    Returns:
        Formatted context string with agent information, or empty string if not found
    """
    try:
        ingestion_service = get_ingestion_service()
        results = ingestion_service.query_agent_info(query, top_k=top_k)

        if not results:
            return ""

        # Format results as context
        context_parts = ["## Agent/Role Information:"]
        for i, result in enumerate(results, 1):
            content = result.get("content", "")
            metadata = result.get("metadata", {})

            if content:
                context_parts.append(f"\n### Result {i}:")
                context_parts.append(content)

                # Add metadata if available
                if metadata.get("agent_name"):
                    context_parts.append(f"Agent: {metadata['agent_name']}")
                if metadata.get("role"):
                    context_parts.append(f"Role: {metadata['role']}")

        return "\n".join(context_parts)

    except Exception as e:
        logging.exception(f"Failed to query agent info: {e}")
        return ""

