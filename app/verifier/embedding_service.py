"""
Embedding Service for the Hospital Bill Verifier.
Uses OpenAI-compatible embedding API to generate vector embeddings for text.

Usage:
    service = EmbeddingService()
    embeddings = service.get_embeddings(["text1", "text2"])
"""

from __future__ import annotations

import logging
import os
from typing import List, Optional

import numpy as np
from openai import OpenAI

logger = logging.getLogger(__name__)


class EmbeddingService:
    """
    Service for generating text embeddings using OpenAI-compatible API.
    
    Supports any OpenAI-compatible endpoint (OpenAI, Azure, local models, etc.)
    Caches embeddings in memory for v1 (no persistence).
    """
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        api_base: Optional[str] = None,
        model: Optional[str] = None,
        dimension: Optional[int] = None,
    ):
        """
        Initialize the embedding service.
        
        Args:
            api_key: OpenAI API key (defaults to OPENAI_API_KEY env var)
            api_base: API base URL (defaults to EMBEDDING_API_BASE env var)
            model: Embedding model name (defaults to EMBEDDING_MODEL env var)
            dimension: Embedding dimension (defaults to EMBEDDING_DIMENSION env var)
        """
        self.api_key = api_key or os.getenv("OPENAI_API_KEY", "")
        self.api_base = api_base or os.getenv("EMBEDDING_API_BASE", "https://api.openai.com/v1")
        self.model = model or os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")
        self.dimension = dimension or int(os.getenv("EMBEDDING_DIMENSION", "1536"))
        
        # Initialize OpenAI client
        self.client = OpenAI(
            api_key=self.api_key,
            base_url=self.api_base,
        )
        
        # In-memory cache: text -> embedding
        self._cache: dict[str, np.ndarray] = {}
        
        logger.info(f"EmbeddingService initialized with model={self.model}, dimension={self.dimension}")
    
    def get_embedding(self, text: str) -> np.ndarray:
        """
        Get embedding for a single text string.
        
        Args:
            text: Input text to embed
            
        Returns:
            numpy array of shape (dimension,)
        """
        # Check cache first
        cache_key = text.strip().lower()
        if cache_key in self._cache:
            return self._cache[cache_key]
        
        # Call API
        try:
            response = self.client.embeddings.create(
                input=[text],
                model=self.model,
            )
            embedding = np.array(response.data[0].embedding, dtype=np.float32)
            
            # Cache the result
            self._cache[cache_key] = embedding
            
            return embedding
            
        except Exception as e:
            logger.error(f"Failed to get embedding for text: {e}")
            raise
    
    def get_embeddings(self, texts: List[str]) -> np.ndarray:
        """
        Get embeddings for multiple text strings (batched).
        
        Args:
            texts: List of input texts to embed
            
        Returns:
            numpy array of shape (len(texts), dimension)
        """
        if not texts:
            return np.array([], dtype=np.float32).reshape(0, self.dimension)
        
        # Check which texts need API calls
        embeddings = []
        texts_to_fetch = []
        fetch_indices = []
        
        for i, text in enumerate(texts):
            cache_key = text.strip().lower()
            if cache_key in self._cache:
                embeddings.append((i, self._cache[cache_key]))
            else:
                texts_to_fetch.append(text)
                fetch_indices.append(i)
        
        # Fetch uncached embeddings from API
        if texts_to_fetch:
            try:
                response = self.client.embeddings.create(
                    input=texts_to_fetch,
                    model=self.model,
                )
                
                for j, item in enumerate(response.data):
                    embedding = np.array(item.embedding, dtype=np.float32)
                    original_idx = fetch_indices[j]
                    cache_key = texts_to_fetch[j].strip().lower()
                    
                    # Cache the result
                    self._cache[cache_key] = embedding
                    embeddings.append((original_idx, embedding))
                    
            except Exception as e:
                logger.error(f"Failed to get embeddings batch: {e}")
                raise
        
        # Sort by original index and stack
        embeddings.sort(key=lambda x: x[0])
        return np.stack([emb for _, emb in embeddings], axis=0)
    
    def clear_cache(self):
        """Clear the in-memory embedding cache."""
        self._cache.clear()
        logger.info("Embedding cache cleared")
    
    @property
    def cache_size(self) -> int:
        """Return the number of cached embeddings."""
        return len(self._cache)


# =============================================================================
# Module-level singleton for convenience
# =============================================================================

_embedding_service: Optional[EmbeddingService] = None


def get_embedding_service() -> EmbeddingService:
    """Get or create the global embedding service instance."""
    global _embedding_service
    if _embedding_service is None:
        _embedding_service = EmbeddingService()
    return _embedding_service
