# /data/inception/app/services/embedding_service.py
"""
Embedding generation service for RAG (Retrieval-Augmented Generation).
Supports OpenAI embeddings and local Ollama embedding models.
"""

import os
import logging
import requests
from typing import List, Optional


def generate_embedding(text: str) -> Optional[List[float]]:
    """
    Generate embedding vector for text using OpenAI or local Ollama model.

    Args:
        text: Text to embed

    Returns:
        Embedding vector (list of floats) or None if generation fails
    """
    if not text or not text.strip():
        logging.warning("Empty text provided for embedding generation")
        return None

    try:
        # Try OpenAI embeddings first (if configured)
        openai_key = os.getenv("OPENAI_API_KEY")
        if openai_key:
            try:
                import openai
                client = openai.OpenAI(api_key=openai_key)
                response = client.embeddings.create(
                    model="text-embedding-3-small",  # 1536 dimensions, fast and cheap
                    input=text
                )
                embedding = response.data[0].embedding
                logging.debug(f"Generated OpenAI embedding: {len(embedding)} dimensions")
                return embedding
            except ImportError:
                logging.warning("openai package not installed, falling back to Ollama")
            except Exception as e:
                logging.warning(f"OpenAI embedding failed: {e}, falling back to Ollama")

        # Fallback: Use local embedding model via Ollama
        embedding_model = os.getenv("OLLAMA_EMBEDDING_MODEL", "nomic-embed-text")
        ollama_url = os.getenv("OLLAMA_URL", "http://127.0.0.1:11434")

        response = requests.post(
            f"{ollama_url}/api/embeddings",
            json={
                "model": embedding_model,
                "prompt": text
            },
            timeout=30
        )
        response.raise_for_status()
        data = response.json()
        embedding = data.get("embedding")

        if embedding:
            logging.debug(f"Generated Ollama embedding: {len(embedding)} dimensions")
            return embedding
        else:
            logging.error("Ollama returned empty embedding")
            return None

    except requests.exceptions.RequestException as e:
        logging.error(f"Failed to generate embedding via Ollama: {e}")
        return None
    except Exception as e:
        logging.exception(f"Unexpected error generating embedding: {e}")
        return None


def batch_generate_embeddings(texts: List[str]) -> List[Optional[List[float]]]:
    """
    Generate embeddings for multiple texts (batched for efficiency).

    Args:
        texts: List of texts to embed

    Returns:
        List of embedding vectors (or None for failed generations)
    """
    embeddings = []
    for text in texts:
        embedding = generate_embedding(text)
        embeddings.append(embedding)
    return embeddings

