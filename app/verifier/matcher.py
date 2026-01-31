"""
Semantic Matcher for the Hospital Bill Verifier.
Uses FAISS for efficient similarity search on embeddings.

Matching logic:
- Hospital: Pick highest similarity match from all tie-up rate sheets
- Category: Match if similarity >= 0.70, else mark all items as MISMATCH
- Item: Match if similarity >= 0.85, else mark as MISMATCH
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import faiss
import numpy as np

from app.verifier.embedding_service import EmbeddingService, get_embedding_service
from app.verifier.models import TieUpCategory, TieUpItem, TieUpRateSheet

logger = logging.getLogger(__name__)


# =============================================================================
# Configuration
# =============================================================================

# Similarity thresholds (loaded from env or defaults)
CATEGORY_SIMILARITY_THRESHOLD = float(os.getenv("CATEGORY_SIMILARITY_THRESHOLD", "0.70"))
ITEM_SIMILARITY_THRESHOLD = float(os.getenv("ITEM_SIMILARITY_THRESHOLD", "0.85"))


# =============================================================================
# Data Classes for Match Results
# =============================================================================

@dataclass
class MatchResult:
    """Result of a semantic match operation."""
    matched_text: Optional[str]
    similarity: float
    index: int  # Index in the original list (-1 if no match)
    
    @property
    def is_match(self) -> bool:
        """Check if this is a valid match (index >= 0)."""
        return self.index >= 0


@dataclass
class HospitalMatch(MatchResult):
    """Hospital match result with tie-up rate sheet reference."""
    rate_sheet: Optional[TieUpRateSheet] = None


@dataclass
class CategoryMatch(MatchResult):
    """Category match result with tie-up category reference."""
    category: Optional[TieUpCategory] = None


@dataclass
class ItemMatch(MatchResult):
    """Item match result with tie-up item reference."""
    item: Optional[TieUpItem] = None


# =============================================================================
# FAISS Index Wrapper
# =============================================================================

class FAISSIndex:
    """
    Wrapper around FAISS index for similarity search.
    Uses inner product (cosine similarity with normalized vectors).
    """
    
    def __init__(self, dimension: int):
        """
        Initialize FAISS index.
        
        Args:
            dimension: Embedding dimension
        """
        self.dimension = dimension
        # Use IndexFlatIP for inner product (cosine similarity with L2 normalized vectors)
        self.index = faiss.IndexFlatIP(dimension)
        self.texts: List[str] = []
    
    def add(self, embeddings: np.ndarray, texts: List[str]):
        """
        Add embeddings to the index.
        
        Args:
            embeddings: Array of shape (n, dimension)
            texts: List of corresponding text strings
        """
        if len(embeddings) == 0:
            return
            
        # L2 normalize for cosine similarity
        faiss.normalize_L2(embeddings)
        self.index.add(embeddings)
        self.texts.extend(texts)
    
    def search(self, query_embedding: np.ndarray, k: int = 1) -> List[Tuple[int, float]]:
        """
        Search for k nearest neighbors.
        
        Args:
            query_embedding: Query vector of shape (dimension,)
            k: Number of results to return
            
        Returns:
            List of (index, similarity_score) tuples
        """
        if self.index.ntotal == 0:
            return []
        
        # Reshape and normalize query
        query = query_embedding.reshape(1, -1).astype(np.float32)
        faiss.normalize_L2(query)
        
        # Search
        k = min(k, self.index.ntotal)
        distances, indices = self.index.search(query, k)
        
        results = []
        for i in range(k):
            idx = int(indices[0][i])
            # Cosine similarity from inner product (already normalized)
            similarity = float(distances[0][i])
            results.append((idx, similarity))
        
        return results
    
    def search_with_threshold(
        self, 
        query_embedding: np.ndarray, 
        threshold: float
    ) -> Optional[Tuple[int, float, str]]:
        """
        Search for best match above threshold.
        
        Args:
            query_embedding: Query vector
            threshold: Minimum similarity score
            
        Returns:
            Tuple of (index, similarity, text) if match found, else None
        """
        results = self.search(query_embedding, k=1)
        if not results:
            return None
            
        idx, similarity = results[0]
        if similarity >= threshold:
            return (idx, similarity, self.texts[idx])
        return None
    
    @property
    def size(self) -> int:
        """Return number of vectors in the index."""
        return self.index.ntotal


# =============================================================================
# Semantic Matcher
# =============================================================================

class SemanticMatcher:
    """
    Main semantic matcher class.
    Builds FAISS indices from tie-up rate sheets and performs matching.
    """
    
    def __init__(self, embedding_service: Optional[EmbeddingService] = None):
        """
        Initialize the semantic matcher.
        
        Args:
            embedding_service: Embedding service instance (uses global if None)
        """
        self.embedding_service = embedding_service or get_embedding_service()
        self.dimension = self.embedding_service.dimension
        
        # Hospital-level index
        self._hospital_index: Optional[FAISSIndex] = None
        self._hospital_rate_sheets: List[TieUpRateSheet] = []
        
        # Per-hospital category indices: hospital_name -> FAISSIndex
        self._category_indices: Dict[str, FAISSIndex] = {}
        self._category_refs: Dict[str, List[TieUpCategory]] = {}
        
        # Per-category item indices: (hospital_name, category_name) -> FAISSIndex
        self._item_indices: Dict[Tuple[str, str], FAISSIndex] = {}
        self._item_refs: Dict[Tuple[str, str], List[TieUpItem]] = {}
        
        logger.info("SemanticMatcher initialized")
    
    def index_rate_sheets(self, rate_sheets: List[TieUpRateSheet]):
        """
        Build FAISS indices from tie-up rate sheets.
        
        This creates:
        1. A hospital-level index for matching bill hospital to tie-up hospitals
        2. Category indices for each hospital
        3. Item indices for each category in each hospital
        
        Args:
            rate_sheets: List of TieUpRateSheet objects
        """
        if not rate_sheets:
            logger.warning("No rate sheets provided for indexing")
            return
        
        logger.info(f"Indexing {len(rate_sheets)} rate sheets...")
        
        self._hospital_rate_sheets = rate_sheets
        
        # 1. Index hospital names
        hospital_names = [rs.hospital_name for rs in rate_sheets]
        hospital_embeddings = self.embedding_service.get_embeddings(hospital_names)
        
        self._hospital_index = FAISSIndex(self.dimension)
        self._hospital_index.add(hospital_embeddings, hospital_names)
        
        # 2. Index categories and items for each hospital
        for rs in rate_sheets:
            hospital_key = rs.hospital_name.lower()
            
            # Category index for this hospital
            if rs.categories:
                category_names = [cat.category_name for cat in rs.categories]
                category_embeddings = self.embedding_service.get_embeddings(category_names)
                
                cat_index = FAISSIndex(self.dimension)
                cat_index.add(category_embeddings, category_names)
                
                self._category_indices[hospital_key] = cat_index
                self._category_refs[hospital_key] = rs.categories
                
                # Item index for each category
                for cat in rs.categories:
                    if cat.items:
                        cat_key = (hospital_key, cat.category_name.lower())
                        item_names = [item.item_name for item in cat.items]
                        item_embeddings = self.embedding_service.get_embeddings(item_names)
                        
                        item_index = FAISSIndex(self.dimension)
                        item_index.add(item_embeddings, item_names)
                        
                        self._item_indices[cat_key] = item_index
                        self._item_refs[cat_key] = cat.items
        
        logger.info(
            f"Indexed: {self._hospital_index.size} hospitals, "
            f"{len(self._category_indices)} category indices, "
            f"{len(self._item_indices)} item indices"
        )
    
    def match_hospital(self, hospital_name: str) -> HospitalMatch:
        """
        Match a bill hospital name to the best tie-up hospital.
        
        Args:
            hospital_name: Hospital name from the bill
            
        Returns:
            HospitalMatch with the best matching rate sheet
        """
        if self._hospital_index is None or self._hospital_index.size == 0:
            logger.warning("No hospital index available")
            return HospitalMatch(
                matched_text=None,
                similarity=0.0,
                index=-1,
                rate_sheet=None
            )
        
        # Get embedding for query hospital
        query_embedding = self.embedding_service.get_embedding(hospital_name)
        
        # Find best match
        results = self._hospital_index.search(query_embedding, k=1)
        if not results:
            return HospitalMatch(
                matched_text=None,
                similarity=0.0,
                index=-1,
                rate_sheet=None
            )
        
        idx, similarity = results[0]
        matched_name = self._hospital_index.texts[idx]
        rate_sheet = self._hospital_rate_sheets[idx]
        
        logger.debug(f"Hospital match: '{hospital_name}' -> '{matched_name}' (sim={similarity:.4f})")
        
        return HospitalMatch(
            matched_text=matched_name,
            similarity=similarity,
            index=idx,
            rate_sheet=rate_sheet
        )
    
    def match_category(
        self, 
        category_name: str, 
        hospital_name: str,
        threshold: float = CATEGORY_SIMILARITY_THRESHOLD
    ) -> CategoryMatch:
        """
        Match a bill category to a tie-up category.
        
        Args:
            category_name: Category name from the bill
            hospital_name: Matched hospital name (from match_hospital)
            threshold: Minimum similarity threshold (default 0.70)
            
        Returns:
            CategoryMatch (similarity < threshold means MISMATCH)
        """
        hospital_key = hospital_name.lower()
        
        if hospital_key not in self._category_indices:
            logger.warning(f"No category index for hospital: {hospital_name}")
            return CategoryMatch(
                matched_text=None,
                similarity=0.0,
                index=-1,
                category=None
            )
        
        cat_index = self._category_indices[hospital_key]
        cat_refs = self._category_refs[hospital_key]
        
        # Get embedding for query category
        query_embedding = self.embedding_service.get_embedding(category_name)
        
        # Find best match
        results = cat_index.search(query_embedding, k=1)
        if not results:
            return CategoryMatch(
                matched_text=None,
                similarity=0.0,
                index=-1,
                category=None
            )
        
        idx, similarity = results[0]
        matched_name = cat_index.texts[idx]
        category = cat_refs[idx]
        
        logger.debug(f"Category match: '{category_name}' -> '{matched_name}' (sim={similarity:.4f})")
        
        # Return match regardless of threshold (caller decides what to do)
        return CategoryMatch(
            matched_text=matched_name,
            similarity=similarity,
            index=idx if similarity >= threshold else -1,
            category=category if similarity >= threshold else None
        )
    
    def match_item(
        self,
        item_name: str,
        hospital_name: str,
        category_name: str,
        threshold: float = ITEM_SIMILARITY_THRESHOLD
    ) -> ItemMatch:
        """
        Match a bill item to a tie-up item.
        
        Args:
            item_name: Item name from the bill
            hospital_name: Matched hospital name
            category_name: Matched category name
            threshold: Minimum similarity threshold (default 0.85)
            
        Returns:
            ItemMatch (similarity < threshold means MISMATCH)
        """
        cat_key = (hospital_name.lower(), category_name.lower())
        
        if cat_key not in self._item_indices:
            logger.warning(f"No item index for: {hospital_name}/{category_name}")
            return ItemMatch(
                matched_text=None,
                similarity=0.0,
                index=-1,
                item=None
            )
        
        item_index = self._item_indices[cat_key]
        item_refs = self._item_refs[cat_key]
        
        # Get embedding for query item
        query_embedding = self.embedding_service.get_embedding(item_name)
        
        # Find best match
        results = item_index.search(query_embedding, k=1)
        if not results:
            return ItemMatch(
                matched_text=None,
                similarity=0.0,
                index=-1,
                item=None
            )
        
        idx, similarity = results[0]
        matched_name = item_index.texts[idx]
        item = item_refs[idx]
        
        logger.debug(f"Item match: '{item_name}' -> '{matched_name}' (sim={similarity:.4f})")
        
        return ItemMatch(
            matched_text=matched_name,
            similarity=similarity,
            index=idx if similarity >= threshold else -1,
            item=item if similarity >= threshold else None
        )
    
    def clear_indices(self):
        """Clear all FAISS indices and references."""
        self._hospital_index = None
        self._hospital_rate_sheets = []
        self._category_indices.clear()
        self._category_refs.clear()
        self._item_indices.clear()
        self._item_refs.clear()
        logger.info("All indices cleared")


# =============================================================================
# Module-level singleton
# =============================================================================

_matcher: Optional[SemanticMatcher] = None


def get_matcher() -> SemanticMatcher:
    """Get or create the global semantic matcher instance."""
    global _matcher
    if _matcher is None:
        _matcher = SemanticMatcher()
    return _matcher
