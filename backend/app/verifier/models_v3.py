"""
Phase-3 Models for Hospital Bill Verifier.

Introduces dual-view output system:
1. Debug View - Full trace with all matching details (developer/internal)
2. Final View - Clean, collapsed view (user/report)

Both views are derived from the same verification run, ensuring consistency.

Phase-3 Principle: One verification, two perspectives
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from app.verifier.models import FailureReason, VerificationStatus


# =============================================================================
# Debug View Models (Full Trace)
# =============================================================================


class CandidateMatch(BaseModel):
    """
    A single candidate match attempt.
    
    Stores details of one tie-up item that was considered
    during the matching process.
    
    This allows full transparency into why certain items were
    accepted or rejected during matching.
    """
    
    candidate_name: str
    similarity_score: float
    category: str
    was_accepted: bool
    rejection_reason: Optional[str] = None


class DebugItemTrace(BaseModel):
    """
    Complete trace of a single bill item verification (Debug View).
    
    Contains every detail of the matching process for developer inspection
    and debugging. Nothing is hidden or collapsed.
    
    Fields include:
    - Original bill text and normalized form
    - Category detection and matching attempts
    - Matching strategy and similarity scores
    - ALL candidates tried (not just best)
    - Best candidate (even if rejected)
    - Final status and amounts
    - Failure reasons and notes
    - Package-specific information
    """
    
    # Original data
    original_bill_text: str
    normalized_item_name: str
    bill_amount: float
    
    # Category detection
    detected_category: str
    category_attempted: str  # May differ if reconciliation occurred
    
    # Matching details
    matching_strategy: str  # "exact" | "fuzzy" | "hybrid" | "hybrid_v2" | "package" | "none"
    semantic_similarity: Optional[float] = None
    token_overlap: Optional[float] = None
    medical_anchor_score: Optional[float] = None
    hybrid_score: Optional[float] = None
    
    # Matching result
    best_candidate: Optional[str] = None  # Even if rejected
    best_candidate_similarity: Optional[float] = None
    matched_item: Optional[str] = None  # Only if accepted
    
    # NEW: All candidates tried (full transparency)
    all_candidates_tried: List[CandidateMatch] = Field(default_factory=list)
    
    # Pricing
    allowed_rate: Optional[float] = None
    allowed_amount: float = 0.0
    extra_amount: float = 0.0
    
    # Final result
    final_status: VerificationStatus
    failure_reason: Optional[FailureReason] = None
    
    # Additional context
    notes: List[str] = Field(default_factory=list)  # e.g., "admin charge", "package-only item"
    reconciliation_attempted: bool = False
    reconciliation_succeeded: bool = False
    all_categories_tried: List[str] = Field(default_factory=list)
    
    # NEW: Package-specific information
    is_package_item: bool = False
    package_components: Optional[List[str]] = None


class DebugCategoryTrace(BaseModel):
    """
    Debug trace for all items in a category.
    
    Preserves original bill order and shows all items including duplicates.
    """
    
    category: str
    items: List[DebugItemTrace] = Field(default_factory=list)


class DebugView(BaseModel):
    """
    Complete debug view of verification (Developer/Internal).
    
    Shows everything:
    - All bill items in original order
    - All matching attempts
    - All similarity scores
    - All candidates (even rejected)
    - All notes and diagnostics
    
    No collapsing, no hiding, full transparency.
    """
    
    hospital: str
    matched_hospital: Optional[str] = None
    hospital_similarity: Optional[float] = None
    
    categories: List[DebugCategoryTrace] = Field(default_factory=list)
    
    # Metadata
    total_items_processed: int
    verification_metadata: Dict[str, Any] = Field(default_factory=dict)


# =============================================================================
# Final View Models (Clean/Collapsed)
# =============================================================================


class FinalItem(BaseModel):
    """
    Clean, user-facing item result (Final View).
    
    Shows only what the user needs to know:
    - Display name (cleaned, human-readable)
    - Final status
    - Amounts
    - Short reason tag (if MISMATCH)
    
    No similarity scores, no candidates, no internal notes.
    """
    
    display_name: str  # Cleaned, human-readable
    final_status: VerificationStatus
    bill_amount: float
    allowed_amount: float = 0.0
    extra_amount: float = 0.0
    
    # For MISMATCH items only
    reason_tag: Optional[FailureReason] = None


class FinalCategory(BaseModel):
    """
    Final view for all items in a category.
    
    Shows only resolved items, one line per bill item.
    Duplicates still appear multiple times (no deduplication).
    """
    
    category: str
    items: List[FinalItem] = Field(default_factory=list)
    
    # Category totals
    total_bill: float = 0.0
    total_allowed: float = 0.0
    total_extra: float = 0.0


class FinalView(BaseModel):
    """
    Clean, user-facing verification report (Final View).
    
    Derived from Debug View, shows only final results:
    - Resolved items per category
    - Clean status indicators
    - Financial totals
    - Short reason tags for mismatches
    
    Readable by non-technical users.
    """
    
    hospital: str
    matched_hospital: Optional[str] = None
    
    categories: List[FinalCategory] = Field(default_factory=list)
    
    # Grand totals
    grand_total_bill: float = 0.0
    grand_total_allowed: float = 0.0
    grand_total_extra: float = 0.0
    
    # Summary counts
    green_count: int = 0
    red_count: int = 0
    mismatch_count: int = 0
    allowed_not_comparable_count: int = 0


# =============================================================================
# Phase-3 Dual View Response
# =============================================================================


class Phase3Response(BaseModel):
    """
    Complete Phase-3 response with dual views.
    
    Contains both Debug and Final views derived from the same verification run.
    Ensures consistency between views while providing different perspectives.
    
    Usage:
    - Use debug_view for development, debugging, and detailed analysis
    - Use final_view for user reports, summaries, and presentations
    """
    
    debug_view: DebugView
    final_view: FinalView
    
    # Validation metadata
    consistency_check: Dict[str, bool] = Field(default_factory=dict)
