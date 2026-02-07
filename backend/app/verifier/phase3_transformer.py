"""
Phase-3 View Transformer for Hospital Bill Verifier.

Transforms verification results into dual views:
1. Debug View - Full trace with all details
2. Final View - Clean, user-facing report

Both views are derived from the same verification run.

Phase-3 Principle: One verification, two perspectives
Phase 4-6 Enhancement: Explicit failure reasoning and candidate tracking
"""

from __future__ import annotations

import logging
from typing import List

from app.verifier.models import VerificationStatus
from app.verifier.models_v2 import Phase2Response
from app.verifier.models_v3 import (
    CandidateMatch,
    DebugCategoryTrace,
    DebugItemTrace,
    DebugView,
    FinalCategory,
    FinalItem,
    FinalView,
    Phase3Response,
)
from app.verifier.failure_reasons import determine_failure_reason
from app.verifier.artifact_detector import is_artifact

logger = logging.getLogger(__name__)


# =============================================================================
# Debug View Builder
# =============================================================================


def build_debug_view(phase2_response: Phase2Response) -> DebugView:
    """
    Build complete debug view from Phase-2 response.
    
    Creates a full trace showing every detail of the verification process:
    - Original bill text and normalized forms
    - All matching attempts and scores
    - All candidates (even rejected) - Phase 4-6 enhancement
    - All notes and diagnostics
    - Enhanced failure reasoning - Phase 4-6 enhancement
    
    Args:
        phase2_response: Complete Phase-2 response
        
    Returns:
        Debug view with full trace
    """
    debug_categories = []
    
    # Group items by category (preserve original order within category)
    category_map = {}
    for agg_item in phase2_response.aggregated_items:
        if agg_item.category not in category_map:
            category_map[agg_item.category] = []
        
        # Create debug trace for each line item
        for line_item in agg_item.line_items:
            # Determine matching strategy
            matching_strategy = "none"
            if line_item.matched_item:
                if line_item.similarity_score and line_item.similarity_score >= 0.95:
                    matching_strategy = "exact"
                elif line_item.similarity_score and line_item.similarity_score >= 0.85:
                    matching_strategy = "fuzzy"
                else:
                    matching_strategy = "hybrid_v2"  # Phase-2 uses hybrid v2
            
            # Build notes
            notes = []
            if agg_item.reconciliation_note:
                notes.append(agg_item.reconciliation_note)
            
            # Get all categories tried
            all_categories_tried = (
                line_item.diagnostics.all_categories_tried
                if line_item.diagnostics
                else [agg_item.category]
            )
            
            # Phase 4-6: Build all_candidates_tried list
            all_candidates_tried = []
            
            # Add best candidate if exists
            if line_item.diagnostics and line_item.diagnostics.best_candidate:
                all_candidates_tried.append(
                    CandidateMatch(
                        candidate_name=line_item.diagnostics.best_candidate,
                        similarity_score=line_item.diagnostics.best_candidate_similarity or 0.0,
                        category=agg_item.category,
                        was_accepted=line_item.matched_item == line_item.diagnostics.best_candidate,
                        rejection_reason=(
                            None if line_item.matched_item == line_item.diagnostics.best_candidate
                            else f"Below threshold (similarity={line_item.diagnostics.best_candidate_similarity:.3f})"
                        )
                    )
                )
            
            # Phase 4-6: Determine if package item
            # Check if item name contains package/bundle keywords
            item_lower = line_item.bill_item.lower()
            is_package = any(
                keyword in item_lower
                for keyword in ["package", "bundle", "combo", "plan"]
            )
            
            # Phase 4-6: Detect if administrative/artifact
            is_admin = is_artifact(line_item.bill_item)
            
            # Phase 4-6: Enhanced failure reason determination
            failure_reason = None
            if line_item.status == VerificationStatus.MISMATCH:
                best_similarity = (
                    line_item.diagnostics.best_candidate_similarity
                    if line_item.diagnostics
                    else 0.0
                )
                
                failure_reason = determine_failure_reason(
                    item_name=line_item.bill_item,
                    normalized_name=line_item.normalized_item_name or line_item.bill_item,
                    category=agg_item.category,
                    best_similarity=best_similarity,
                    all_categories_tried=all_categories_tried,
                    is_package=is_package,
                    is_admin=is_admin,
                )
                
                # Add failure reason to notes
                notes.append(f"Failure reason: {failure_reason.value}")
            elif line_item.diagnostics and line_item.diagnostics.failure_reason:
                # Use existing failure reason if available
                failure_reason = line_item.diagnostics.failure_reason
            
            # Create debug trace
            debug_trace = DebugItemTrace(
                original_bill_text=line_item.bill_item,
                normalized_item_name=line_item.normalized_item_name or line_item.bill_item,
                bill_amount=line_item.bill_amount,
                detected_category=agg_item.original_category or agg_item.category,
                category_attempted=agg_item.category,
                matching_strategy=matching_strategy,
                semantic_similarity=line_item.similarity_score,
                token_overlap=None,  # Would need to extract from diagnostics
                medical_anchor_score=None,  # Would need to extract from diagnostics
                hybrid_score=line_item.similarity_score,
                best_candidate=(
                    line_item.diagnostics.best_candidate
                    if line_item.diagnostics
                    else None
                ),
                best_candidate_similarity=(
                    line_item.diagnostics.best_candidate_similarity
                    if line_item.diagnostics
                    else None
                ),
                matched_item=line_item.matched_item,
                all_candidates_tried=all_candidates_tried,  # Phase 4-6: NEW
                allowed_rate=agg_item.allowed_per_unit if line_item.matched_item else None,
                allowed_amount=line_item.allowed_amount,
                extra_amount=line_item.extra_amount,
                final_status=line_item.status,
                failure_reason=failure_reason,  # Phase 4-6: Enhanced
                notes=notes,
                reconciliation_attempted=agg_item.original_category is not None,
                reconciliation_succeeded=agg_item.reconciliation_note is not None,
                all_categories_tried=all_categories_tried,
                is_package_item=is_package,  # Phase 4-6: NEW
                package_components=None,  # Phase 4-6: NEW (would need package data)
            )
            
            category_map[agg_item.category].append(debug_trace)
    
    # Build category traces
    for category, items in category_map.items():
        debug_categories.append(
            DebugCategoryTrace(category=category, items=items)
        )
    
    return DebugView(
        hospital=phase2_response.hospital,
        matched_hospital=phase2_response.matched_hospital,
        hospital_similarity=phase2_response.hospital_similarity,
        categories=debug_categories,
        total_items_processed=len(phase2_response.phase1_line_items),
        verification_metadata=phase2_response.processing_metadata,
    )


# =============================================================================
# Final View Builder
# =============================================================================


def build_final_view(debug_view: DebugView) -> FinalView:
    """
    Build clean final view from debug view.
    
    Transforms debug trace into user-facing report:
    - Clean display names
    - Simple status indicators
    - Financial totals
    - Short reason tags only
    
    Args:
        debug_view: Complete debug view
        
    Returns:
        Clean final view for users
    """
    final_categories = []
    
    grand_total_bill = 0.0
    grand_total_allowed = 0.0
    grand_total_extra = 0.0
    
    green_count = 0
    red_count = 0
    mismatch_count = 0
    allowed_not_comparable_count = 0
    
    for debug_category in debug_view.categories:
        final_items = []
        category_total_bill = 0.0
        category_total_allowed = 0.0
        category_total_extra = 0.0
        
        for debug_item in debug_category.items:
            # Create clean display name
            display_name = debug_item.matched_item or debug_item.normalized_item_name
            
            # Create final item
            final_item = FinalItem(
                display_name=display_name,
                final_status=debug_item.final_status,
                bill_amount=debug_item.bill_amount,
                allowed_amount=debug_item.allowed_amount,
                extra_amount=debug_item.extra_amount,
                reason_tag=(
                    debug_item.failure_reason
                    if debug_item.final_status == VerificationStatus.MISMATCH
                    else None
                ),
            )
            
            final_items.append(final_item)
            
            # Update category totals
            category_total_bill += debug_item.bill_amount
            category_total_allowed += debug_item.allowed_amount
            category_total_extra += debug_item.extra_amount
            
            # Update counts
            if debug_item.final_status == VerificationStatus.GREEN:
                green_count += 1
            elif debug_item.final_status == VerificationStatus.RED:
                red_count += 1
            elif debug_item.final_status == VerificationStatus.MISMATCH:
                mismatch_count += 1
            elif debug_item.final_status == VerificationStatus.ALLOWED_NOT_COMPARABLE:
                allowed_not_comparable_count += 1
        
        final_categories.append(
            FinalCategory(
                category=debug_category.category,
                items=final_items,
                total_bill=category_total_bill,
                total_allowed=category_total_allowed,
                total_extra=category_total_extra,
            )
        )
        
        # Update grand totals
        grand_total_bill += category_total_bill
        grand_total_allowed += category_total_allowed
        grand_total_extra += category_total_extra
    
    return FinalView(
        hospital=debug_view.hospital,
        matched_hospital=debug_view.matched_hospital,
        categories=final_categories,
        grand_total_bill=grand_total_bill,
        grand_total_allowed=grand_total_allowed,
        grand_total_extra=grand_total_extra,
        green_count=green_count,
        red_count=red_count,
        mismatch_count=mismatch_count,
        allowed_not_comparable_count=allowed_not_comparable_count,
    )


# =============================================================================
# Consistency Validation
# =============================================================================


def validate_consistency(debug_view: DebugView, final_view: FinalView) -> dict:
    """
    Validate consistency between debug and final views.
    
    Ensures:
    - No items disappeared
    - Item counts match
    - Totals match
    - Duplicate items preserved
    
    Args:
        debug_view: Debug view
        final_view: Final view
        
    Returns:
        Dictionary of validation results
    """
    checks = {}
    
    # Count items in both views
    debug_item_count = sum(len(cat.items) for cat in debug_view.categories)
    final_item_count = sum(len(cat.items) for cat in final_view.categories)
    
    checks["item_count_match"] = debug_item_count == final_item_count
    checks["debug_item_count"] = debug_item_count
    checks["final_item_count"] = final_item_count
    
    # Verify totals match
    debug_total_bill = sum(
        item.bill_amount
        for cat in debug_view.categories
        for item in cat.items
    )
    
    checks["totals_match"] = abs(debug_total_bill - final_view.grand_total_bill) < 0.01
    checks["debug_total_bill"] = debug_total_bill
    checks["final_total_bill"] = final_view.grand_total_bill
    
    # Check category count
    checks["category_count_match"] = len(debug_view.categories) == len(
        final_view.categories
    )
    
    # Overall validation
    checks["all_checks_passed"] = all(
        [
            checks["item_count_match"],
            checks["totals_match"],
            checks["category_count_match"],
        ]
    )
    
    if checks["all_checks_passed"]:
        logger.info("✅ Consistency validation passed")
    else:
        logger.warning("⚠️ Consistency validation failed")
        logger.warning(f"Checks: {checks}")
    
    return checks


# =============================================================================
# Phase-3 Transformer
# =============================================================================


def transform_to_phase3(phase2_response: Phase2Response) -> Phase3Response:
    """
    Transform Phase-2 response into Phase-3 dual-view response.
    
    Creates both Debug and Final views from the same verification run,
    ensuring consistency and providing different perspectives.
    
    Args:
        phase2_response: Complete Phase-2 response
        
    Returns:
        Phase-3 response with dual views
        
    Example:
        >>> phase3_response = transform_to_phase3(phase2_response)
        >>> phase3_response.debug_view.total_items_processed
        8
        >>> phase3_response.final_view.grand_total_bill
        14873.80
        >>> phase3_response.consistency_check['all_checks_passed']
        True
    """
    logger.info("=" * 80)
    logger.info("Transforming to Phase-3 dual-view response")
    logger.info("=" * 80)
    
    # Build debug view
    logger.info("Building debug view (full trace)...")
    debug_view = build_debug_view(phase2_response)
    
    # Build final view from debug view
    logger.info("Building final view (clean report)...")
    final_view = build_final_view(debug_view)
    
    # Validate consistency
    logger.info("Validating consistency between views...")
    consistency_check = validate_consistency(debug_view, final_view)
    
    logger.info("=" * 80)
    logger.info(
        f"Phase-3 transformation complete: "
        f"{debug_view.total_items_processed} items processed"
    )
    logger.info(f"Debug view: {len(debug_view.categories)} categories")
    logger.info(f"Final view: {len(final_view.categories)} categories")
    logger.info(f"Consistency: {'✅ PASSED' if consistency_check['all_checks_passed'] else '❌ FAILED'}")
    logger.info("=" * 80)
    
    return Phase3Response(
        debug_view=debug_view,
        final_view=final_view,
        consistency_check=consistency_check,
    )


# =============================================================================
# Testing
# =============================================================================

if __name__ == "__main__":
    print("Phase-3 view transformer module loaded successfully!")
    print("Use transform_to_phase3() to create dual-view response.")
