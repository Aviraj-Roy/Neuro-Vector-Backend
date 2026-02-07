"""
Phase-2 Processor for Hospital Bill Verifier.

Main orchestrator that transforms Phase-1 output into Phase-2 aggregated comparison.

Processing Pipeline:
1. Build Rate Cache - Cache allowed rates for re-use
2. Aggregate Items - Group duplicates while preserving breakdown
3. Resolve Statuses - Apply priority-based status resolution
4. Reconcile Categories - Retry MISMATCH items in alternative categories
5. Calculate Financial Summary - Generate multi-level totals

Phase-2 Principle: Non-destructive aggregation with full traceability
"""

from __future__ import annotations

import logging
from typing import List

from app.verifier.aggregator import (
    aggregate_line_items,
    build_rate_cache,
    resolve_aggregate_status,
)
from app.verifier.financial import build_financial_summary
from app.verifier.models import ItemVerificationResult, VerificationResponse
from app.verifier.models_v2 import Phase2Response
from app.verifier.reconciler import reconcile_categories

logger = logging.getLogger(__name__)


# =============================================================================
# Phase-2 Main Processor
# =============================================================================


def process_phase2(
    phase1_response: VerificationResponse, hospital_name: str
) -> Phase2Response:
    """
    Transform Phase-1 output into Phase-2 aggregated comparison.
    
    Applies the complete Phase-2 processing pipeline to convert Phase-1's
    exhaustive item-level listing into a clinically and financially meaningful
    comparison layer.
    
    Processing Steps:
    1. Build rate cache from Phase-1 matches
    2. Aggregate line items by (normalized_name, matched_ref, category)
    3. Resolve final status for each aggregated group
    4. Attempt category reconciliation for MISMATCH items
    5. Calculate multi-level financial summary
    
    Args:
        phase1_response: Complete Phase-1 verification response
        hospital_name: Hospital name for reconciliation
        
    Returns:
        Phase2Response with aggregated, reconciled, and financially summarized data
        
    Example:
        >>> phase2_response = process_phase2(phase1_response, "Apollo Hospital")
        >>> len(phase2_response.aggregated_items)
        5
        >>> phase2_response.financial_summary.grand_totals.total_bill
        14873.80
    """
    logger.info("=" * 80)
    logger.info("Starting Phase-2 processing")
    logger.info("=" * 80)
    
    # Step 1: Build rate cache
    logger.info("Step 1/5: Building rate cache...")
    rate_cache = build_rate_cache(phase1_response)
    
    # Step 2: Aggregate items
    logger.info("Step 2/5: Aggregating line items...")
    aggregated_items = aggregate_line_items(
        phase1_response=phase1_response, rate_cache=rate_cache
    )
    
    # Step 3: Resolve statuses
    logger.info("Step 3/5: Resolving aggregate statuses...")
    for agg_item in aggregated_items:
        agg_item.status = resolve_aggregate_status(agg_item.line_items)
    
    # Count statuses before reconciliation
    pre_reconciliation_stats = {
        "green": sum(1 for item in aggregated_items if item.status.value == "GREEN"),
        "red": sum(1 for item in aggregated_items if item.status.value == "RED"),
        "mismatch": sum(
            1 for item in aggregated_items if item.status.value == "MISMATCH"
        ),
    }
    
    logger.info(
        f"Pre-reconciliation: GREEN={pre_reconciliation_stats['green']}, "
        f"RED={pre_reconciliation_stats['red']}, "
        f"MISMATCH={pre_reconciliation_stats['mismatch']}"
    )
    
    # Step 4: Category reconciliation (for MISMATCH items)
    logger.info("Step 4/5: Attempting category reconciliation...")
    reconciled_items = reconcile_categories(
        aggregated_items=aggregated_items,
        hospital_name=hospital_name,
        rate_cache=rate_cache,
    )
    
    # Count statuses after reconciliation
    post_reconciliation_stats = {
        "green": sum(1 for item in reconciled_items if item.status.value == "GREEN"),
        "red": sum(1 for item in reconciled_items if item.status.value == "RED"),
        "mismatch": sum(
            1 for item in reconciled_items if item.status.value == "MISMATCH"
        ),
    }
    
    logger.info(
        f"Post-reconciliation: GREEN={post_reconciliation_stats['green']}, "
        f"RED={post_reconciliation_stats['red']}, "
        f"MISMATCH={post_reconciliation_stats['mismatch']}"
    )
    
    reconciliation_improvement = (
        pre_reconciliation_stats["mismatch"]
        - post_reconciliation_stats["mismatch"]
    )
    if reconciliation_improvement > 0:
        logger.info(
            f"✅ Reconciliation improved match rate: "
            f"{reconciliation_improvement} items reconciled"
        )
    
    # Step 5: Calculate financial totals
    logger.info("Step 5/5: Calculating financial summary...")
    financial_summary = build_financial_summary(reconciled_items)
    
    # Collect all Phase-1 line items for traceability
    phase1_line_items: List[ItemVerificationResult] = []
    for category_result in phase1_response.results:
        phase1_line_items.extend(category_result.items)
    
    # Build Phase-2 response
    response = Phase2Response(
        hospital=phase1_response.hospital,
        matched_hospital=phase1_response.matched_hospital,
        hospital_similarity=phase1_response.hospital_similarity,
        phase1_line_items=phase1_line_items,
        aggregated_items=reconciled_items,
        financial_summary=financial_summary,
        processing_metadata={
            "phase1_items_count": len(phase1_line_items),
            "phase2_aggregated_count": len(reconciled_items),
            "rate_cache_size": len(rate_cache),
            "reconciliation_improvement": reconciliation_improvement,
            "pre_reconciliation_stats": pre_reconciliation_stats,
            "post_reconciliation_stats": post_reconciliation_stats,
        },
    )
    
    logger.info("=" * 80)
    logger.info(
        f"Phase-2 processing complete: "
        f"{len(phase1_line_items)} line items → {len(reconciled_items)} aggregated items"
    )
    logger.info(
        f"Financial Summary: "
        f"Bill=₹{financial_summary.grand_totals.total_bill:.2f}, "
        f"Allowed=₹{financial_summary.grand_totals.total_allowed:.2f}, "
        f"Extra=₹{financial_summary.grand_totals.total_extra:.2f}"
    )
    logger.info("=" * 80)
    
    return response


# =============================================================================
# Testing
# =============================================================================

if __name__ == "__main__":
    print("Phase-2 processor module loaded successfully!")
    print("Use process_phase2() to transform Phase-1 output into Phase-2 response.")
