# /data/inception/app/services/cloudflare_vectorize_service.py
"""
Cloudflare Vectorize Service for querying and updating product information vector index.
Integrates with Cloudflare's Vectorize API for RAG (Retrieval-Augmented Generation).
"""

import os
import requests
import logging
from typing import List, Dict, Optional, Any
import json


class CloudflareVectorizeService:
    """Service for interacting with Cloudflare Vectorize index."""
    
    def __init__(self):
        self.api_key = os.getenv("CLOUDFLARE_API_KEY")
        self.account_id = os.getenv("CLOUDFLARE_ACCOUNT_ID")
        self.index_name = os.getenv("CLOUDFLARE_VECTORIZE_INDEX_NAME", "product-index")
        # Cloudflare Vectorize can be accessed via:
        # 1. Direct REST API (if available)
        # 2. Cloudflare Worker proxy (recommended for production)
        self.worker_url = os.getenv("CLOUDFLARE_WORKER_URL")  # Optional: Worker proxy URL
        if self.account_id:
            self.api_base = f"https://api.cloudflare.com/client/v4/accounts/{self.account_id}/vectorize/indexes/{self.index_name}"
        else:
            self.api_base = None
        self.enabled = bool(self.api_key and self.account_id) or bool(self.worker_url)
        
        if not self.enabled:
            logging.warning("Cloudflare Vectorize not configured (missing API key/account ID or Worker URL)")
    
    def _get_headers(self) -> Dict[str, str]:
        """Get authentication headers for Cloudflare API."""
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
    
    def query(
        self,
        query_vector: List[float],
        top_k: int = 5,
        filter: Optional[Dict[str, Any]] = None,
        return_metadata: bool = True
    ) -> List[Dict[str, Any]]:
        """
        Query the Vectorize index for similar vectors.
        
        Args:
            query_vector: Embedding vector to search for
            top_k: Number of results to return
            filter: Optional metadata filter (e.g., {"category": "tea"})
            return_metadata: Whether to return metadata with results
            
        Returns:
            List of matching vectors with scores and metadata
        """
        if not self.enabled:
            logging.warning("Cloudflare Vectorize query skipped - service not configured")
            return []
        
        try:
            # Use Worker proxy if configured, otherwise try direct API
            if self.worker_url:
                url = f"{self.worker_url}/query"
                headers = {"Content-Type": "application/json"}  # Worker may not need auth
            else:
                url = f"{self.api_base}/query"
                headers = self._get_headers()
            
            payload = {
                "vector": query_vector,
                "topK": top_k,
                "returnMetadata": return_metadata
            }
            
            if filter:
                payload["filter"] = filter
            
            response = requests.post(
                url,
                json=payload,
                headers=headers,
                timeout=10
            )
            response.raise_for_status()
            data = response.json()
            
            # Extract results from Cloudflare response format
            if "result" in data and "matches" in data["result"]:
                return data["result"]["matches"]
            elif "matches" in data:
                return data["matches"]
            else:
                logging.warning(f"Unexpected Vectorize response format: {data}")
                return []
                
        except requests.exceptions.RequestException as e:
            logging.error(f"Cloudflare Vectorize query failed: {e}")
            if hasattr(e, 'response') and e.response is not None:
                try:
                    error_body = e.response.json()
                    logging.error(f"Error response: {error_body}")
                except:
                    logging.error(f"Error response text: {e.response.text[:500]}")
            return []
        except Exception as e:
            logging.exception(f"Unexpected error in Vectorize query: {e}")
            return []
    
    def upsert(
        self,
        vectors: List[Dict[str, Any]]
    ) -> bool:
        """
        Upsert vectors into the index.
        
        Args:
            vectors: List of dicts with keys:
                - id: Unique identifier
                - values: Embedding vector
                - metadata: Optional metadata dict
                
        Returns:
            True if successful, False otherwise
        """
        if not self.enabled:
            logging.warning("Cloudflare Vectorize upsert skipped - service not configured")
            return False
        
        try:
            # Use Worker proxy if configured, otherwise try direct API
            if self.worker_url:
                url = f"{self.worker_url}/upsert"
                headers = {"Content-Type": "application/json"}
            else:
                url = f"{self.api_base}/upsert"
                headers = self._get_headers()
            
            payload = {
                "vectors": vectors
            }
            
            response = requests.post(
                url,
                json=payload,
                headers=headers,
                timeout=30
            )
            response.raise_for_status()
            
            logging.info(f"Successfully upserted {len(vectors)} vectors to Vectorize index")
            return True
            
        except requests.exceptions.RequestException as e:
            logging.error(f"Cloudflare Vectorize upsert failed: {e}")
            if hasattr(e, 'response') and e.response is not None:
                try:
                    error_body = e.response.json()
                    logging.error(f"Error response: {error_body}")
                except:
                    logging.error(f"Error response text: {e.response.text[:500]}")
            return False
        except Exception as e:
            logging.exception(f"Unexpected error in Vectorize upsert: {e}")
            return False
    
    def delete(self, vector_ids: List[str]) -> bool:
        """
        Delete vectors from the index by ID.
        
        Args:
            vector_ids: List of vector IDs to delete
            
        Returns:
            True if successful, False otherwise
        """
        if not self.enabled:
            logging.warning("Cloudflare Vectorize delete skipped - service not configured")
            return False
        
        try:
            # Use Worker proxy if configured, otherwise try direct API
            if self.worker_url:
                url = f"{self.worker_url}/delete"
                headers = {"Content-Type": "application/json"}
            else:
                url = f"{self.api_base}/delete"
                headers = self._get_headers()
            
            payload = {
                "ids": vector_ids
            }
            
            response = requests.post(
                url,
                json=payload,
                headers=headers,
                timeout=10
            )
            response.raise_for_status()
            
            logging.info(f"Successfully deleted {len(vector_ids)} vectors from Vectorize index")
            return True
            
        except requests.exceptions.RequestException as e:
            logging.error(f"Cloudflare Vectorize delete failed: {e}")
            return False
        except Exception as e:
            logging.exception(f"Unexpected error in Vectorize delete: {e}")
            return False


# Global service instance
_vectorize_service = None


def get_vectorize_service() -> CloudflareVectorizeService:
    """Get or create the global Vectorize service instance."""
    global _vectorize_service
    if _vectorize_service is None:
        _vectorize_service = CloudflareVectorizeService()
    return _vectorize_service


def query_product_info(
    query_text: str,
    top_k: int = 5,
    filter: Optional[Dict[str, Any]] = None
) -> List[Dict[str, Any]]:
    """
    Query product information from Vectorize index using text query.
    This function generates embeddings for the query text and searches the index.
    
    Args:
        query_text: Natural language query (e.g., "green tea benefits")
        top_k: Number of results to return
        filter: Optional metadata filter
        
    Returns:
        List of product information matches
    """
    # Generate embedding for query text
    embedding = generate_embedding(query_text)
    if not embedding:
        logging.warning(f"Failed to generate embedding for query: {query_text}")
        return []
    
    # Query Vectorize index
    service = get_vectorize_service()
    results = service.query(
        query_vector=embedding,
        top_k=top_k,
        filter=filter,
        return_metadata=True
    )
    
    return results


def generate_embedding(text: str) -> Optional[List[float]]:
    """
    Generate embedding vector for text using OpenAI or local model.
    
    Args:
        text: Text to embed
        
    Returns:
        Embedding vector or None if generation fails
    """
    try:
        # Try OpenAI embeddings first (if configured)
        openai_key = os.getenv("OPENAI_API_KEY")
        if openai_key:
            import openai
            client = openai.OpenAI(api_key=openai_key)
            response = client.embeddings.create(
                model="text-embedding-3-small",  # or text-embedding-ada-002
                input=text
            )
            return response.data[0].embedding
        
        # Fallback: Use local embedding model (Ollama with embedding model)
        # This requires an embedding model to be available via Ollama
        embedding_model = os.getenv("OLLAMA_EMBEDDING_MODEL", "nomic-embed-text")
        ollama_url = os.getenv("OLLAMA_URL", "http://127.0.0.1:11434")
        
        response = requests.post(
            f"{ollama_url}/api/embeddings",
            json={
                "model": embedding_model,
                "prompt": text
            },
            timeout=10
        )
        response.raise_for_status()
        data = response.json()
        return data.get("embedding")
        
    except Exception as e:
        logging.error(f"Failed to generate embedding: {e}")
        return None


def upsert_product(
    product_id: str,
    product_text: str,
    metadata: Optional[Dict[str, Any]] = None
) -> bool:
    """
    Upsert a product into the Vectorize index.
    
    Args:
        product_id: Unique product identifier
        product_text: Product description/content to embed
        metadata: Optional metadata (e.g., {"category": "tea", "price": 29.99})
        
    Returns:
        True if successful, False otherwise
    """
    # Generate embedding
    embedding = generate_embedding(product_text)
    if not embedding:
        logging.warning(f"Failed to generate embedding for product: {product_id}")
        return False
    
    # Prepare vector for upsert
    vector = {
        "id": product_id,
        "values": embedding
    }
    
    if metadata:
        vector["metadata"] = metadata
    
    # Upsert to Vectorize
    service = get_vectorize_service()
    return service.upsert([vector])

