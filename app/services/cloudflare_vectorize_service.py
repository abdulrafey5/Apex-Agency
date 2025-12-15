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
from services.embedding_service import generate_embedding


class CloudflareVectorizeService:
    """Service for interacting with Cloudflare Vectorize index."""

    def __init__(self):
        self.api_key = os.getenv("CLOUDFLARE_API_KEY")
        self.account_id = os.getenv("CLOUDFLARE_ACCOUNT_ID")
        self.index_name = os.getenv("CLOUDFLARE_VECTORIZE_INDEX_NAME", "product-index")
        self.worker_url = os.getenv("CLOUDFLARE_WORKER_URL")
        if self.account_id:
            self.api_base = f"https://api.cloudflare.com/client/v4/accounts/{self.account_id}/vectorize/indexes/{self.index_name}"
        else:
            self.api_base = None
        self.enabled = False  # Explicitly disabled for now

        logging.info("Cloudflare Vectorize is disabled (deferred configuration)")

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
            logging.info("Cloudflare Vectorize query skipped - disabled")
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
            logging.info("Cloudflare Vectorize upsert skipped - disabled")
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
            logging.info("Cloudflare Vectorize delete skipped - disabled")
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


_vectorize_service = None


def get_vectorize_service() -> CloudflareVectorizeService:
    """Get or create the global Vectorize service instance."""
    global _vectorize_service
    if _vectorize_service is None:
        _vectorize_service = CloudflareVectorizeService()
    return _vectorize_service

