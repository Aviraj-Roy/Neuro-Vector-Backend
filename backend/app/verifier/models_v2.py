"""
Phase-2 Models for Hospital Bill Verifier.

This module defines enhanced models for Phase-2 aggregation layer:
- Aggregated items with line-item breakdown
- Enhanced diagnostics with hybrid score breakdown
- Financial summary models (category + grand totals)
- Phase-2 response structure

Phase-2 Principle: Non-destructive aggregation with full traceability
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from app.verifier.models import (
    FailureReason,
    ItemVerificationResult,
    VerificationStatus,
)


# =============================================================================
# Enhanced Diagnostics (Phase-2)
# =============================================================================


class MismatchDiagnosticsV2(BaseModel):
    """
    Enhanced diagnostics for Phase-2 with deep explainability.
    
    Provides comprehensive information about why an item couldn't be matched,
    including hybrid score breakdown and all reconciliation attempts.
    """
    
    normalized_item_name: str
    best_candidate: Optional[str] = None  # Only if similarity > 0.5
    best_candidate_similarity: Optional[float] = None
    category_attempted: str
    all_categories_tried: List[str] = Field(default_factory=list)  # Phase-2: Reconciliation tracking
    failure_reason: FailureReason
    hybrid_score_breakdown: Optional[Dict[str, float]] = None  # Phase-2: Detailed scoring


# =============================================================================
# Aggregated Item (Phase-2)
# =============================================================================


class AggregatedItem(BaseModel):
    """
    Aggregated item with line-item breakdown.
    
    Groups multiple line items by (normalized_name, matched_reference, category)
    while preserving full breakdown for traceability.
    
    Example:
        NICORANDIL 5MG (x4 occurrences)
          Total Bill: ₹78.80
          Allowed (per unit): ₹49.25
          Applied Allowed: ₹49.25 × 4 = ₹197.00
          Status: GREEN
          
          Breakdown:
            - LineItemID: item_001 | Bill: ₹19.70
            - LineItemID: item_002 | Bill: ₹19.70
            - LineItemID: item_003 | Bill: ₹19.70
            - LineItemID: item_004 | Bill: ₹19.70
    """
    
    # Identification
    normalized_name: str
    matched_reference: Optional[str] = None
    category: str
    original_category: Optional[str] = None  # For reconciliation tracking
    
    # Aggregation data
    occurrences: int
    total_bill: float
    allowed_per_unit: float
    total_allowed: float
    total_extra: float
    
    # Status
    status: VerificationStatus
    
    # Breakdown (preserve Phase-1 data)
    line_items: List[ItemVerificationResult] = Field(default_factory=list)
    
    # Reconciliation
    reconciliation_note: Optional[str] = None
    
    # Diagnostics (for MISMATCH/ALLOWED_NOT_COMPARABLE)
    diagnostics: Optional[MismatchDiagnosticsV2] = None


# =============================================================================
# Financial Summary Models (Phase-2)
# =============================================================================


class CategoryTotals(BaseModel):
    """
    Financial totals for a single category.
    
    Aggregates all items within a category to provide category-level summary.
    """
    
    category: str
    total_bill: float
    total_allowed: float
    total_extra: float
    green_count: int
    red_count: int
    mismatch_count: int
    ignored_count: int = 0


class GrandTotals(BaseModel):
    """
    Overall financial summary across all categories.
    
    Provides top-level financial metrics for the entire bill.
    """
    
    total_bill: float
    total_allowed: float
    total_extra: float
    total_allowed_not_comparable: float
    green_count: int
    red_count: int
    mismatch_count: int
    ignored_count: int


class FinancialSummary(BaseModel):
    """
    Complete financial breakdown with category and grand totals.
    
    Provides 4 levels of financial aggregation:
    1. Line-item totals (preserved in AggregatedItem.line_items)
    2. Aggregated item totals (in AggregatedItem)
    3. Category totals (in category_totals)
    4. Grand totals (in grand_totals)
    """
    
    category_totals: List[CategoryTotals] = Field(default_factory=list)
    grand_totals: GrandTotals


# =============================================================================
# Phase-2 Response
# =============================================================================


class Phase2Response(BaseModel):
    """
    Complete Phase-2 verification response.
    
    Transforms Phase-1's exhaustive item-level output into a clinically
    and financially meaningful comparison layer.
    
    Key Features:
    - Aggregated items with line-item breakdown
    - Category reconciliation applied
    - Multi-level financial summary
    - Deep diagnostics for mismatches
    - Full traceability to Phase-1 data
    """
    
    # Hospital matching (from Phase-1)
    hospital: str
    matched_hospital: Optional[str] = None
    hospital_similarity: Optional[float] = None
    
    # Phase-1 data (preserved for traceability)
    phase1_line_items: List[ItemVerificationResult] = Field(default_factory=list)
    
    # Phase-2 aggregated data
    aggregated_items: List[AggregatedItem] = Field(default_factory=list)
    
    # Financial summary
    financial_summary: FinancialSummary
    
    # Metadata
    processing_metadata: Dict[str, Any] = Field(default_factory=dict)
