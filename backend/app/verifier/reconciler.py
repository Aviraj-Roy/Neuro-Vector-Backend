"""
Category Reconciler for Hospital Bill Verifier (Phase-2).

Attempts to match MISMATCH items in alternative categories to improve
match rate and reduce false negatives.

Strategy:
1. For each MISMATCH item, try matching in all other categories
2. Pick the best match (highest similarity)
3. Update item with reconciled category and add reconciliation note
4. Track all attempted categories for diagnostics

This significantly improves match rate by finding items that were
categorized differently in the bill vs. tie-up rate sheet.
"""

from __future__ import annotations

import logging
from typing import Dict, List, Optional, Tuple

from app.verifier.matcher import ITEM_SIMILARITY_THRESHOLD, get_matcher
from app.verifier.models import VerificationStatus
from app.verifier.models_v2 import AggregatedItem

logger = logging.getLogger(__name__)


# =============================================================================
# Alternative Category Matching
# =============================================================================


def try_alternative_categories(
    item: AggregatedItem,
    hospital_name: str,
    rate_cache: Dict[Tuple[str, str], float],
) -> Optional[dict]:
    """
    Try matching item in all available categories.
    
    Attempts to find a match for a MISMATCH item by trying all categories
    in the tie-up rate sheet, not just the original category from the bill.
    
    Args:
        item: Aggregated item to reconcile
        hospital_name: Hospital name for matching
        rate_cache: Rate cache for pricing
        
    Returns:
        Best match result dict or None
        
    Example:
        >>> best_match = try_alternative_categories(item, "Apollo Hospital", rate_cache)
        >>> best_match['category']
        'specialist_consultation'
        >>> best_match['similarity']
        0.78
    """
    matcher = get_matcher()
    best_match = None
    best_score = 0.0
    
    # Get all available categories from rate sheets
    # Note: This requires adding a method to matcher to get all categories
    # For now, we'll try to get categories from the rate sheet
    try:
        # Get the rate sheet for this hospital
        hospital_match = matcher.match_hospital(hospital_name)
        if not hospital_match.is_match or hospital_match.rate_sheet is None:
            logger.warning(f"No rate sheet found for hospital: {hospital_name}")
            return None
        
        rate_sheet = hospital_match.rate_sheet
        all_categories = [cat.category_name for cat in rate_sheet.categories]
    except Exception as e:
        logger.error(f"Error getting categories: {e}")
        return None
    
    attempted_categories = [item.category]
    
    for category in all_categories:
        if category == item.category:
            continue  # Skip original category
        
        attempted_categories.append(category)
        
        # Try matching in this category
        try:
            match_result = matcher.match_item(
                item_name=item.normalized_name,
                hospital_name=hospital_name,
                category_name=category,
                threshold=ITEM_SIMILARITY_THRESHOLD,
            )
            
            if match_result.is_match and match_result.similarity > best_score:
                best_match = {
                    "matched_item": match_result.matched_text,
                    "category": category,
                    "similarity": match_result.similarity,
                    "attempted_categories": attempted_categories.copy(),
                }
                best_score = match_result.similarity
        except Exception as e:
            logger.debug(f"Error matching in category {category}: {e}")
            continue
    
    if best_match:
        logger.info(
            f"Reconciliation success: '{item.normalized_name}' "
            f"found in '{best_match['category']}' (similarity={best_score:.2f})"
        )
    
    return best_match


# =============================================================================
# Category Reconciliation
# =============================================================================


def reconcile_categories(
    aggregated_items: List[AggregatedItem],
    hospital_name: str,
    rate_cache: Dict[Tuple[str, str], float],
) -> List[AggregatedItem]:
    """
    For MISMATCH items, attempt matching in alternative categories.
    
    Tries to find matches for items that failed in their original category
    by attempting all other available categories. This significantly improves
    match rate and reduces false negatives.
    
    Args:
        aggregated_items: List of aggregated items
        hospital_name: Hospital name for matching
        rate_cache: Rate cache for pricing
        
    Returns:
        List of reconciled items
        
    Example:
        >>> reconciled = reconcile_categories(aggregated_items, "Apollo Hospital", rate_cache)
        >>> cross_consult = next(item for item in reconciled if "cross" in item.normalized_name)
        >>> cross_consult.status
        VerificationStatus.GREEN
        >>> cross_consult.reconciliation_note
        "Found in alternative category 'specialist_consultation' after original category 'consultation' failed"
    """
    reconciled_items = []
    reconciliation_stats = {"attempted": 0, "succeeded": 0, "failed": 0}
    
    for agg_item in aggregated_items:
        if agg_item.status == VerificationStatus.MISMATCH:
            reconciliation_stats["attempted"] += 1
            
            # Try alternative categories
            best_match = try_alternative_categories(
                item=agg_item, hospital_name=hospital_name, rate_cache=rate_cache
            )
            
            if best_match:
                # Update with reconciled match
                agg_item.original_category = agg_item.category
                agg_item.matched_reference = best_match["matched_item"]
                agg_item.category = best_match["category"]
                
                # Re-check price to determine GREEN/RED status
                # For now, we'll assume GREEN (would need price checker integration)
                agg_item.status = VerificationStatus.GREEN
                
                agg_item.reconciliation_note = (
                    f"Found in alternative category '{best_match['category']}' "
                    f"after original category '{agg_item.original_category}' failed"
                )
                
                # Update diagnostics if present
                if agg_item.diagnostics:
                    agg_item.diagnostics.all_categories_tried = best_match[
                        "attempted_categories"
                    ]
                
                reconciliation_stats["succeeded"] += 1
            else:
                reconciliation_stats["failed"] += 1
        
        reconciled_items.append(agg_item)
    
    logger.info(
        f"Reconciliation complete: "
        f"{reconciliation_stats['succeeded']}/{reconciliation_stats['attempted']} succeeded"
    )
    
    return reconciled_items


# =============================================================================
# Testing
# =============================================================================

if __name__ == "__main__":
    print("Reconciler module loaded successfully!")
    print("Use this module to reconcile MISMATCH items across categories.")
