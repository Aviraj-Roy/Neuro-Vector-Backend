"""
Phase-2 Aggregator for Hospital Bill Verifier.

Provides core aggregation functionality:
1. Rate Cache Builder - Cache allowed rates to avoid redundant lookups
2. Item Aggregator - Group line items while preserving breakdown
3. Status Resolver - Resolve final status for aggregated groups

Phase-2 Principle: Non-destructive aggregation with full traceability
"""

from __future__ import annotations

import logging
from collections import defaultdict
from typing import Dict, List, Tuple

from app.verifier.models import VerificationResponse, VerificationStatus
from app.verifier.models_v2 import AggregatedItem

logger = logging.getLogger(__name__)


# =============================================================================
# Rate Cache Builder
# =============================================================================


def build_rate_cache(
    phase1_response: VerificationResponse,
) -> Dict[Tuple[str, str], float]:
    """
    Build cache of allowed rates for matched items.
    
    Cache Key: (normalized_item_name, matched_reference)
    Cache Value: allowed_rate (per unit)
    
    This cache enables rate re-use for duplicate items, avoiding redundant
    lookups and ensuring consistency across aggregated groups.
    
    Args:
        phase1_response: Complete Phase-1 verification response
        
    Returns:
        Dictionary mapping (normalized_name, matched_ref) to allowed_rate
        
    Example:
        >>> rate_cache = build_rate_cache(phase1_response)
        >>> rate_cache[("nicorandil_5mg", "NICORANDIL 5MG")]
        49.25
    """
    rate_cache = {}
    
    for category_result in phase1_response.results:
        for item_result in category_result.items:
            # Only cache successfully matched items (GREEN or RED)
            if item_result.matched_item and item_result.status in [
                VerificationStatus.GREEN,
                VerificationStatus.RED,
            ]:
                cache_key = (
                    item_result.normalized_item_name or item_result.bill_item,
                    item_result.matched_item,
                )
                
                # Store per-unit rate
                # Note: For items with quantity > 1, this is already the per-unit rate
                rate_cache[cache_key] = item_result.allowed_amount
    
    logger.info(f"Built rate cache with {len(rate_cache)} entries")
    return rate_cache


# =============================================================================
# Item Aggregator
# =============================================================================


def aggregate_line_items(
    phase1_response: VerificationResponse,
    rate_cache: Dict[Tuple[str, str], float],
) -> List[AggregatedItem]:
    """
    Group line items by (normalized_name, matched_reference, category).
    
    Creates aggregated groups while preserving full line-item breakdown
    for traceability. Each aggregated item contains:
    - Total amounts (bill, allowed, extra)
    - Occurrence count
    - Per-unit rate (from cache)
    - Full list of contributing line items
    
    Args:
        phase1_response: Complete Phase-1 verification response
        rate_cache: Pre-built rate cache
        
    Returns:
        List of aggregated items with line-item breakdown
        
    Example:
        >>> aggregated = aggregate_line_items(phase1_response, rate_cache)
        >>> nicorandil = aggregated[0]
        >>> nicorandil.occurrences
        4
        >>> nicorandil.total_bill
        78.80
        >>> len(nicorandil.line_items)
        4
    """
    aggregation_map = defaultdict(list)
    
    # Group line items by (normalized_name, matched_ref, category)
    for category_result in phase1_response.results:
        for item_result in category_result.items:
            # Group key: (normalized_name, matched_ref, category)
            group_key = (
                item_result.normalized_item_name or item_result.bill_item,
                item_result.matched_item,
                category_result.category,
            )
            
            aggregation_map[group_key].append(item_result)
    
    # Build aggregated items
    aggregated_items = []
    
    for group_key, line_items in aggregation_map.items():
        normalized_name, matched_ref, category = group_key
        
        # Calculate totals
        total_bill = sum(item.bill_amount for item in line_items)
        total_allowed = sum(item.allowed_amount for item in line_items)
        total_extra = sum(item.extra_amount for item in line_items)
        
        # Get cached rate (if available)
        cache_key = (normalized_name, matched_ref)
        allowed_per_unit = rate_cache.get(cache_key, 0.0)
        
        # Create aggregated item (status will be resolved later)
        aggregated_items.append(
            AggregatedItem(
                normalized_name=normalized_name,
                matched_reference=matched_ref,
                category=category,
                occurrences=len(line_items),
                total_bill=total_bill,
                allowed_per_unit=allowed_per_unit,
                total_allowed=total_allowed,
                total_extra=total_extra,
                line_items=line_items,  # Preserve breakdown
                status=VerificationStatus.MISMATCH,  # Placeholder, will be resolved
            )
        )
    
    logger.info(
        f"Aggregated {sum(len(cat.items) for cat in phase1_response.results)} "
        f"line items into {len(aggregated_items)} groups"
    )
    
    return aggregated_items


# =============================================================================
# Status Resolver
# =============================================================================


def resolve_aggregate_status(line_items: List) -> VerificationStatus:
    """
    Resolve final status for aggregated group.
    
    Priority-based resolution:
    1. RED - Any RED present (overcharge detected)
    2. MISMATCH - Any MISMATCH present (item not found)
    3. GREEN - Only GREEN + ALLOWED_NOT_COMPARABLE (within limits)
    4. ALLOWED_NOT_COMPARABLE - Only non-comparable items
    5. IGNORED_ARTIFACT - Only artifacts
    
    Args:
        line_items: List of line items in the group
        
    Returns:
        Final resolved status
        
    Examples:
        >>> resolve_aggregate_status([GREEN, GREEN, GREEN, RED])
        VerificationStatus.RED
        
        >>> resolve_aggregate_status([GREEN, GREEN, ALLOWED_NOT_COMPARABLE])
        VerificationStatus.GREEN
        
        >>> resolve_aggregate_status([MISMATCH])
        VerificationStatus.MISMATCH
    """
    from app.verifier.artifact_detector import is_artifact
    
    statuses = [item.status for item in line_items]
    
    # Check for artifacts first
    if all(is_artifact(item.bill_item) for item in line_items):
        return VerificationStatus.IGNORED_ARTIFACT
    
    # Priority-based resolution
    if VerificationStatus.RED in statuses:
        return VerificationStatus.RED
    elif VerificationStatus.MISMATCH in statuses:
        return VerificationStatus.MISMATCH
    elif VerificationStatus.GREEN in statuses:
        return VerificationStatus.GREEN
    elif VerificationStatus.ALLOWED_NOT_COMPARABLE in statuses:
        return VerificationStatus.ALLOWED_NOT_COMPARABLE
    else:
        # Fallback to IGNORED_ARTIFACT
        return VerificationStatus.IGNORED_ARTIFACT


# =============================================================================
# Testing
# =============================================================================

if __name__ == "__main__":
    print("Aggregator module loaded successfully!")
    print("Use this module to build rate cache and aggregate items.")
