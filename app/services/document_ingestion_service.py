# /data/inception/app/services/document_ingestion_service.py
"""
Document Ingestion Service for vectorizing and storing documents.
Handles parsing, chunking, embedding generation, and storage in both
Cloudflare Vectorize and PostgreSQL (pgvector).
"""

import os
import logging
import re
from typing import List, Dict, Any, Optional, Tuple
from services.embedding_service import generate_embedding, batch_generate_embeddings
from services.cloudflare_vectorize_service import get_vectorize_service
from services.db_service import get_db_service


class DocumentIngestionService:
    """Service for ingesting, chunking, and vectorizing documents."""

    def __init__(self):
        self.vectorize_service = get_vectorize_service()
        self.db_service = get_db_service()
        self.chunk_size = 512  # tokens (approximate)
        self.chunk_overlap = 50  # tokens

    def chunk_text(
        self,
        text: str,
        chunk_size: int = None,
        chunk_overlap: int = None
    ) -> List[Dict[str, Any]]:
        """
        Chunk text into smaller pieces for embedding.

        Args:
            text: Text to chunk
            chunk_size: Approximate chunk size in tokens (default: self.chunk_size)
            chunk_overlap: Overlap between chunks in tokens (default: self.chunk_overlap)

        Returns:
            List of chunk dicts with keys: text, chunk_index, start_char, end_char
        """
        chunk_size = chunk_size or self.chunk_size
        chunk_overlap = chunk_overlap or self.chunk_overlap

        # Simple chunking by characters (approximate 4 chars per token)
        char_chunk_size = chunk_size * 4
        char_overlap = chunk_overlap * 4

        chunks = []
        start = 0
        chunk_index = 0

        while start < len(text):
            end = min(start + char_chunk_size, len(text))
            chunk_text = text[start:end]

            # Try to break at sentence boundaries
            if end < len(text):
                # Look for sentence endings in the last 100 chars
                last_period = chunk_text.rfind('.', max(0, len(chunk_text) - 100))
                last_newline = chunk_text.rfind('\n', max(0, len(chunk_text) - 100))
                break_point = max(last_period, last_newline)

                if break_point > len(chunk_text) * 0.7:  # Only break if we're not too early
                    chunk_text = chunk_text[:break_point + 1]
                    end = start + len(chunk_text)

            chunks.append({
                "text": chunk_text.strip(),
                "chunk_index": chunk_index,
                "start_char": start,
                "end_char": end
            })

            chunk_index += 1
            start = end - char_overlap  # Overlap for context

        return chunks

    def parse_marketing_department_yaml(self, yaml_content: str) -> Dict[str, Any]:
        """
        Parse the Marketing Department YAML-like structure.
        Returns structured data for vectorization.

        Args:
            yaml_content: YAML-like content string

        Returns:
            Dict with department structure
        """
        # This is a simple parser for the specific format provided
        # For production, consider using a proper YAML parser

        result = {
            "department": {
                "name": "Marketing Department",
                "manager": {},
                "agents": [],
                "general_guidelines": {},
                "communication": {},
                "quality_standards": {}
            }
        }

        # Extract manager info
        manager_match = re.search(r'manager:\s*\n\s*name:\s*(\w+)', yaml_content)
        if manager_match:
            result["department"]["manager"]["name"] = manager_match.group(1)

        title_match = re.search(r'title:\s*(.+?)(?:\n|responsibilities:)', yaml_content)
        if title_match:
            result["department"]["manager"]["title"] = title_match.group(1).strip()

        # Extract responsibilities (simple regex-based extraction)
        resp_section = re.search(r'responsibilities:\s*\n((?:\s*-\s*.+\n?)+)', yaml_content)
        if resp_section:
            responsibilities = re.findall(r'-\s*(.+?)(?:\n|$)', resp_section.group(1))
            result["department"]["manager"]["responsibilities"] = responsibilities

        # Extract agents
        agents_section = re.search(r'agents:\s*\n((?:\s*-\s*name:.+?(?=\s*-\s*name:|\s*quality_standards:|\Z))+)', yaml_content, re.DOTALL)
        if agents_section:
            agent_blocks = re.split(r'\n\s*-\s*name:', agents_section.group(1))
            for block in agent_blocks:
                if not block.strip():
                    continue

                agent = {"name": "", "role": "", "responsibilities": [], "tools": []}

                name_match = re.search(r'name:\s*(\w+)', block)
                if name_match:
                    agent["name"] = name_match.group(1)

                role_match = re.search(r'role:\s*(.+?)(?:\n|responsibilities:)', block)
                if role_match:
                    agent["role"] = role_match.group(1).strip()

                resp_match = re.search(r'responsibilities:\s*\n((?:\s*-\s*.+\n?)+)', block)
                if resp_match:
                    agent["responsibilities"] = re.findall(r'-\s*(.+?)(?:\n|$)', resp_match.group(1))

                tools_match = re.search(r'tools:\s*\n((?:\s*-\s*.+\n?)+)', block)
                if tools_match:
                    agent["tools"] = re.findall(r'-\s*(.+?)(?:\n|$)', tools_match.group(1))

                if agent["name"]:
                    result["department"]["agents"].append(agent)

        return result

    def vectorize_document(
        self,
        document_text: str,
        document_id: str,
        document_type: str = "agent_library",
        metadata: Optional[Dict[str, Any]] = None,
        parse_structure: bool = False
    ) -> Tuple[int, int]:
        """
        Vectorize a document and store in both Vectorize and PostgreSQL.

        Args:
            document_text: Full document text
            document_id: Unique identifier for the document
            document_type: Type of document (e.g., "agent_library", "sop", "department")
            metadata: Optional metadata dict
            parse_structure: If True, try to parse structured format (YAML-like)

        Returns:
            Tuple of (chunks_created, vectors_stored)
        """
        # Parse structure if requested (for Marketing Department doc)
        if parse_structure and "department:" in document_text.lower():
            try:
                structured = self.parse_marketing_department_yaml(document_text)
                # Convert structured data back to searchable text chunks
                document_text = self._structured_to_text(structured)
            except Exception as e:
                logging.warning(f"Failed to parse structure, using raw text: {e}")

        # Chunk the document
        chunks = self.chunk_text(document_text)
        logging.info(f"Chunked document {document_id} into {len(chunks)} chunks")

        if not chunks:
            logging.warning(f"No chunks created for document {document_id}")
            return 0, 0

        # Generate embeddings for all chunks
        chunk_texts = [chunk["text"] for chunk in chunks]
        embeddings = batch_generate_embeddings(chunk_texts)

        if not embeddings or all(e is None for e in embeddings):
            logging.error(f"Failed to generate embeddings for document {document_id}")
            return 0, 0

        # Prepare metadata for each chunk
        vectors_cloudflare = []
        vectors_postgres = []

        for i, (chunk, embedding) in enumerate(zip(chunks, embeddings)):
            if embedding is None:
                continue

            chunk_id = f"{document_id}_chunk_{i}"
            chunk_metadata = {
                "document_id": document_id,
                "document_type": document_type,
                "chunk_index": i,
                **(metadata or {})
            }

            # Prepare for Cloudflare Vectorize
            vectors_cloudflare.append({
                "id": chunk_id,
                "values": embedding,
                "metadata": chunk_metadata
            })

            # Prepare for PostgreSQL
            vectors_postgres.append({
                "content": chunk["text"],
                "embedding": embedding,
                "metadata": chunk_metadata,
                "source_id": chunk_id,
                "source_type": document_type
            })

        # Store in Cloudflare Vectorize
        cloudflare_count = 0
        if self.vectorize_service.enabled:
            # Batch upsert to Vectorize (Cloudflare may have limits)
            batch_size = 100
            for i in range(0, len(vectors_cloudflare), batch_size):
                batch = vectors_cloudflare[i:i + batch_size]
                if self.vectorize_service.upsert(batch):
                    cloudflare_count += len(batch)
                else:
                    logging.warning(f"Failed to upsert batch {i//batch_size + 1} to Cloudflare Vectorize")

        # Store in PostgreSQL
        postgres_count = 0
        for vec in vectors_postgres:
            try:
                self.db_service.upsert_semantic_memory(
                    content=vec["content"],
                    embedding=vec["embedding"],
                    metadata=vec["metadata"],
                    source_type=vec["source_type"],
                    source_id=vec["source_id"]
                )
                postgres_count += 1
            except Exception as e:
                logging.error(f"Failed to store chunk in PostgreSQL: {e}")

        logging.info(f"Vectorized document {document_id}: {len(chunks)} chunks, "
                    f"{cloudflare_count} in Vectorize, {postgres_count} in PostgreSQL")

        return len(chunks), postgres_count

    def _structured_to_text(self, structured: Dict[str, Any]) -> str:
        """Convert structured department data to searchable text."""
        lines = []

        dept = structured.get("department", {})
        lines.append(f"Department: {dept.get('name', 'Unknown')}")
        lines.append("")

        # Manager
        manager = dept.get("manager", {})
        if manager:
            lines.append(f"Manager: {manager.get('name', 'Unknown')} - {manager.get('title', '')}")
            if manager.get("responsibilities"):
                lines.append("Manager Responsibilities:")
                for resp in manager["responsibilities"]:
                    lines.append(f"  - {resp}")
            lines.append("")

        # Agents
        agents = dept.get("agents", [])
        if agents:
            lines.append("Agents:")
            for agent in agents:
                lines.append(f"\nAgent: {agent.get('name', 'Unknown')}")
                lines.append(f"Role: {agent.get('role', 'Unknown')}")
                if agent.get("responsibilities"):
                    lines.append("Responsibilities:")
                    for resp in agent["responsibilities"]:
                        lines.append(f"  - {resp}")
                if agent.get("tools"):
                    lines.append("Tools:")
                    for tool in agent["tools"]:
                        lines.append(f"  - {tool}")
                lines.append("")

        # Guidelines
        guidelines = dept.get("general_guidelines", {})
        if guidelines:
            lines.append("General Guidelines:")
            for key, value in guidelines.items():
                if isinstance(value, str):
                    lines.append(f"{key}: {value}")
            lines.append("")

        return "\n".join(lines)

    def query_agent_info(
        self,
        query: str,
        top_k: int = 5
    ) -> List[Dict[str, Any]]:
        """
        Query for agent/role information using RAG.

        Args:
            query: Natural language query (e.g., "who is Sophie?", "what does Colby do?")
            top_k: Number of results to return

        Returns:
            List of matching chunks with metadata
        """
        # Generate embedding for query
        query_embedding = generate_embedding(query)
        if not query_embedding:
            logging.warning(f"Failed to generate embedding for query: {query}")
            return []

        results = []

        # Query PostgreSQL semantic memory
        try:
            pg_results = self.db_service.semantic_search(
                query_embedding=query_embedding,
                match_threshold=0.6,
                match_count=top_k,
                filter_metadata={"document_type": "agent_library"}
            )
            results.extend(pg_results)
        except Exception as e:
            logging.error(f"PostgreSQL semantic search failed: {e}")

        # Query Cloudflare Vectorize if enabled
        if self.vectorize_service.enabled:
            try:
                vectorize_results = self.vectorize_service.query(
                    query_vector=query_embedding,
                    top_k=top_k,
                    filter={"document_type": "agent_library"},
                    return_metadata=True
                )
                # Convert Vectorize format to our format
                for result in vectorize_results:
                    results.append({
                        "content": result.get("metadata", {}).get("text", ""),
                        "metadata": result.get("metadata", {}),
                        "similarity": result.get("score", 0.0)
                    })
            except Exception as e:
                logging.error(f"Cloudflare Vectorize query failed: {e}")

        # Sort by similarity and deduplicate
        results = sorted(results, key=lambda x: x.get("similarity", 0.0), reverse=True)

        # Simple deduplication by content
        seen = set()
        unique_results = []
        for result in results:
            content = result.get("content", "")
            if content and content not in seen:
                seen.add(content)
                unique_results.append(result)
                if len(unique_results) >= top_k:
                    break

        return unique_results


# Global service instance
_ingestion_service = None


def get_ingestion_service() -> DocumentIngestionService:
    """Get or create the global ingestion service instance."""
    global _ingestion_service
    if _ingestion_service is None:
        _ingestion_service = DocumentIngestionService()
    return _ingestion_service

