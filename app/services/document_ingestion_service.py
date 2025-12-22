# /data/inception/app/services/document_ingestion_service.py
from typing import List, Dict, Any
from services.embedding_service import EmbeddingService

embedding_service = EmbeddingService()

class DocumentIngestionService:
    """Ingest documents and create embeddings for semantic memory."""

    def __init__(self):
        self.embedding_service = embedding_service

    def ingest_document(self, chat_id: int, text_chunks: List[str], embeddings: List[List[float]], metadata_list: List[Dict[str, Any]] = None):
        """Ingest multiple text chunks and store embeddings."""
        for i, chunk in enumerate(text_chunks):
            metadata = metadata_list[i] if metadata_list and i < len(metadata_list) else {}
            self.embedding_service.store_embedding(chat_id, chunk, embeddings[i], metadata)
