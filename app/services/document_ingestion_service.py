# /data/inception/app/services/document_ingestion_service.py
from typing import List, Dict, Any, Optional
from services.db_service import get_db_service

class DocumentIngestionService:
    """Ingest documents and create embeddings for semantic memory."""

    def __init__(self):
        self.db_service = get_db_service()

    def ingest_document(self, chat_id: int, text_chunks: List[str], embeddings: List[List[float]], metadata_list: Optional[List[Dict[str, Any]]] = None):
        """Ingest multiple text chunks and store embeddings."""
        for i, chunk in enumerate(text_chunks):
            metadata = metadata_list[i] if metadata_list and i < len(metadata_list) else {}
            self.db_service.upsert_semantic_memory(
                content=chunk,
                embedding=embeddings[i],
                metadata=metadata,
                source_type="document",
                source_id=f"chat_{chat_id}_chunk_{i}"
            )
