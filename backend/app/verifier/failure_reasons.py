"""
Failure Reason Determination for Hospital Bill Verifier.

Implements priority-based logic to determine the specific reason
why a bill item failed to match against tie-up rates.

Phase 4-6 Enhancement: Explicit failure reasoning for MISMATCH items.
"""

from __future__ import annotations

import logging
from typing import List, Optional

from app.verifier.models import FailureReason

logger = logging.getLogger(__name__)


# =============================================================================
# Failure Reason Determination
# =============================================================================


def determine_failure_reason(
    item_name: str,
    normalized_name: str,
    category: str,
    best_similarity: float,
    all_categories_tried: List[str],
    is_package: bool = False,
    is_admin: bool = False,
    threshold: float = 0.85,
    min_similarity: float = 0.5,
) -> FailureReason:
    """
    Determine the specific failure reason for a MISMATCH item.
    
    Uses priority-based logic to classify why an item failed to match:
    
    Priority Order:
    1. ADMIN_CHARGE - If administrative/artifact (highest priority)
    2. PACKAGE_ONLY - If only exists in packages
    3. CATEGORY_CONFLICT - If exists in other category with good match
    4. LOW_SIMILARITY - If best match below threshold but above minimum
    5. NOT_IN_TIEUP - If nothing close exists (default)
    
    Args:
        item_name: Original bill item name
        normalized_name: Normalized item name
        category: Category where matching was attempted
        best_similarity: Highest similarity score achieved
        all_categories_tried: List of all categories attempted
        is_package: Whether item is a package/bundle
        is_admin: Whether item is administrative/artifact
        threshold: Similarity threshold for acceptance (default: 0.85)
        min_similarity: Minimum similarity to consider (default: 0.5)
        
    Returns:
        FailureReason enum value
        
    Examples:
        >>> determine_failure_reason(
        ...     item_name="Page 1 of 2",
        ...     normalized_name="page 1 of 2",
        ...     category="misc",
        ...     best_similarity=0.0,
        ...     all_categories_tried=["misc"],
        ...     is_admin=True
        ... )
        FailureReason.ADMIN_CHARGE
        
        >>> determine_failure_reason(
        ...     item_name="Health Checkup Package",
        ...     normalized_name="health checkup package",
        ...     category="diagnostics",
        ...     best_similarity=0.65,
        ...     all_categories_tried=["diagnostics"],
        ...     is_package=True
        ... )
        FailureReason.PACKAGE_ONLY
        
        >>> determine_failure_reason(
        ...     item_name="Specialist Consultation",
        ...     normalized_name="specialist consultation",
        ...     category="consultation",
        ...     best_similarity=0.88,
        ...     all_categories_tried=["consultation", "specialist_consultation"]
        ... )
        FailureReason.CATEGORY_CONFLICT
    """
    
    # Priority 1: Administrative/Artifact items
    if is_admin:
        logger.debug(
            f"Item '{item_name}' classified as ADMIN_CHARGE (artifact/administrative)"
        )
        return FailureReason.ADMIN_CHARGE
    
    # Priority 2: Package-only items
    if is_package:
        logger.debug(
            f"Item '{item_name}' classified as PACKAGE_ONLY "
            f"(similarity={best_similarity:.3f})"
        )
        return FailureReason.PACKAGE_ONLY
    
    # Priority 3: Category conflict
    # Item exists in tie-up but in a different category
    # Criteria: Multiple categories tried AND good similarity in alternative category
    if len(all_categories_tried) > 1 and best_similarity >= threshold:
        logger.debug(
            f"Item '{item_name}' classified as CATEGORY_CONFLICT "
            f"(found in alternative category with similarity={best_similarity:.3f})"
        )
        return FailureReason.CATEGORY_CONFLICT
    
    # Priority 4: Low similarity
    # Item has a close match but below acceptance threshold
    if best_similarity >= min_similarity and best_similarity < threshold:
        logger.debug(
            f"Item '{item_name}' classified as LOW_SIMILARITY "
            f"(similarity={best_similarity:.3f}, threshold={threshold})"
        )
        return FailureReason.LOW_SIMILARITY
    
    # Priority 5: Not in tie-up (default)
    # No close match found anywhere
    logger.debug(
        f"Item '{item_name}' classified as NOT_IN_TIEUP "
        f"(best_similarity={best_similarity:.3f} < min_similarity={min_similarity})"
    )
    return FailureReason.NOT_IN_TIEUP


def get_failure_reason_description(reason: FailureReason) -> str:
    """
    Get human-readable description of failure reason.
    
    Args:
        reason: FailureReason enum value
        
    Returns:
        Human-readable description
    """
    descriptions = {
        FailureReason.NOT_IN_TIEUP: "Item not found in tie-up rate sheet",
        FailureReason.LOW_SIMILARITY: "Best match below acceptance threshold",
        FailureReason.PACKAGE_ONLY: "Item only exists as part of a package",
        FailureReason.ADMIN_CHARGE: "Administrative charge or OCR artifact",
        FailureReason.CATEGORY_CONFLICT: "Item found in different category",
    }
    
    return descriptions.get(reason, "Unknown failure reason")


def should_retry_in_alternative_category(
    failure_reason: FailureReason,
    best_similarity: float,
    min_similarity: float = 0.5,
) -> bool:
    """
    Determine if item should be retried in alternative categories.
    
    Retry logic:
    - NOT_IN_TIEUP: Yes, might exist in other category
    - LOW_SIMILARITY: Yes, if similarity > min_similarity
    - PACKAGE_ONLY: No, package issue won't be resolved by category change
    - ADMIN_CHARGE: No, artifact won't match anywhere
    - CATEGORY_CONFLICT: No, already found in alternative category
    
    Args:
        failure_reason: Current failure reason
        best_similarity: Best similarity achieved
        min_similarity: Minimum similarity to consider retry
        
    Returns:
        True if should retry in alternative categories
    """
    
    # Don't retry admin charges or artifacts
    if failure_reason == FailureReason.ADMIN_CHARGE:
        return False
    
    # Don't retry package-only items (won't help)
    if failure_reason == FailureReason.PACKAGE_ONLY:
        return False
    
    # Don't retry if already found in alternative category
    if failure_reason == FailureReason.CATEGORY_CONFLICT:
        return False
    
    # Retry if not in tie-up (might exist elsewhere)
    if failure_reason == FailureReason.NOT_IN_TIEUP:
        return True
    
    # Retry low similarity if above minimum threshold
    if failure_reason == FailureReason.LOW_SIMILARITY:
        return best_similarity >= min_similarity
    
    return False


# =============================================================================
# Testing
# =============================================================================

if __name__ == "__main__":
    print("Failure Reason Determination Module")
    print("=" * 80)
    
    # Test cases
    test_cases = [
        {
            "name": "Administrative charge",
            "item": "Page 1 of 2",
            "category": "misc",
            "similarity": 0.0,
            "categories_tried": ["misc"],
            "is_admin": True,
            "expected": FailureReason.ADMIN_CHARGE,
        },
        {
            "name": "Package item",
            "item": "Health Checkup Package",
            "category": "diagnostics",
            "similarity": 0.65,
            "categories_tried": ["diagnostics"],
            "is_package": True,
            "expected": FailureReason.PACKAGE_ONLY,
        },
        {
            "name": "Category conflict",
            "item": "Specialist Consultation",
            "category": "consultation",
            "similarity": 0.88,
            "categories_tried": ["consultation", "specialist_consultation"],
            "expected": FailureReason.CATEGORY_CONFLICT,
        },
        {
            "name": "Low similarity",
            "item": "Some Medicine",
            "category": "medicines",
            "similarity": 0.72,
            "categories_tried": ["medicines"],
            "expected": FailureReason.LOW_SIMILARITY,
        },
        {
            "name": "Not in tie-up",
            "item": "Unknown Item",
            "category": "misc",
            "similarity": 0.35,
            "categories_tried": ["misc"],
            "expected": FailureReason.NOT_IN_TIEUP,
        },
    ]
    
    print("\nTest Cases:")
    print("-" * 80)
    
    for test in test_cases:
        result = determine_failure_reason(
            item_name=test["item"],
            normalized_name=test["item"].lower(),
            category=test["category"],
            best_similarity=test["similarity"],
            all_categories_tried=test["categories_tried"],
            is_package=test.get("is_package", False),
            is_admin=test.get("is_admin", False),
        )
        
        status = "✅ PASS" if result == test["expected"] else "❌ FAIL"
        print(f"\n{status} {test['name']}")
        print(f"  Item: {test['item']}")
        print(f"  Similarity: {test['similarity']:.2f}")
        print(f"  Expected: {test['expected'].value}")
        print(f"  Got: {result.value}")
        print(f"  Description: {get_failure_reason_description(result)}")
    
    print("\n" + "=" * 80)
    print("All tests completed!")
