"""
Financial Aggregator for Hospital Bill Verifier (Phase-2).

Calculates multi-level financial totals:
1. Line-item totals (preserved in AggregatedItem.line_items)
2. Aggregated item totals (in AggregatedItem)
3. Category totals (calculated here)
4. Grand totals (calculated here)

Provides complete financial breakdown for audit and reporting.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from typing import Dict, List

from app.verifier.models import VerificationStatus
from app.verifier.models_v2 import (
    AggregatedItem,
    CategoryTotals,
    FinancialSummary,
    GrandTotals,
)

logger = logging.getLogger(__name__)


# =============================================================================
# Category Totals Calculation
# =============================================================================


def calculate_category_totals(
    aggregated_items: List[AggregatedItem],
) -> List[CategoryTotals]:
    """
    Calculate financial totals per category.
    
    Aggregates all items within each category to provide category-level
    financial summary including amounts and status counts.
    
    Args:
        aggregated_items: List of aggregated items
        
    Returns:
        List of category totals
        
    Example:
        >>> category_totals = calculate_category_totals(aggregated_items)
        >>> medicines = next(cat for cat in category_totals if cat.category == "medicines")
        >>> medicines.total_bill
        103.80
        >>> medicines.green_count
        1
        >>> medicines.red_count
        1
    """
    category_map = defaultdict(
        lambda: {
            "total_bill": 0.0,
            "total_allowed": 0.0,
            "total_extra": 0.0,
            "green_count": 0,
            "red_count": 0,
            "mismatch_count": 0,
            "ignored_count": 0,
        }
    )
    
    # Aggregate by category
    for agg_item in aggregated_items:
        cat_data = category_map[agg_item.category]
        cat_data["total_bill"] += agg_item.total_bill
        cat_data["total_allowed"] += agg_item.total_allowed
        cat_data["total_extra"] += agg_item.total_extra
        
        # Count by status
        if agg_item.status == VerificationStatus.GREEN:
            cat_data["green_count"] += 1
        elif agg_item.status == VerificationStatus.RED:
            cat_data["red_count"] += 1
        elif agg_item.status == VerificationStatus.MISMATCH:
            cat_data["mismatch_count"] += 1
        elif agg_item.status == VerificationStatus.IGNORED_ARTIFACT:
            cat_data["ignored_count"] += 1
    
    # Convert to CategoryTotals objects
    category_totals = [
        CategoryTotals(category=category, **data)
        for category, data in category_map.items()
    ]
    
    logger.info(f"Calculated totals for {len(category_totals)} categories")
    return category_totals


# =============================================================================
# Grand Totals Calculation
# =============================================================================


def calculate_grand_totals(aggregated_items: List[AggregatedItem]) -> GrandTotals:
    """
    Calculate overall financial totals across all categories.
    
    Provides top-level financial metrics for the entire bill including
    total amounts and status counts.
    
    Args:
        aggregated_items: List of aggregated items
        
    Returns:
        Grand totals
        
    Example:
        >>> grand_totals = calculate_grand_totals(aggregated_items)
        >>> grand_totals.total_bill
        14873.80
        >>> grand_totals.total_allowed
        12712.00
        >>> grand_totals.green_count
        3
    """
    return GrandTotals(
        total_bill=sum(item.total_bill for item in aggregated_items),
        total_allowed=sum(item.total_allowed for item in aggregated_items),
        total_extra=sum(item.total_extra for item in aggregated_items),
        total_allowed_not_comparable=sum(
            item.total_bill
            for item in aggregated_items
            if item.status == VerificationStatus.ALLOWED_NOT_COMPARABLE
        ),
        green_count=sum(
            1 for item in aggregated_items if item.status == VerificationStatus.GREEN
        ),
        red_count=sum(
            1 for item in aggregated_items if item.status == VerificationStatus.RED
        ),
        mismatch_count=sum(
            1 for item in aggregated_items if item.status == VerificationStatus.MISMATCH
        ),
        ignored_count=sum(
            1
            for item in aggregated_items
            if item.status == VerificationStatus.IGNORED_ARTIFACT
        ),
    )


# =============================================================================
# Financial Summary Builder
# =============================================================================


def build_financial_summary(aggregated_items: List[AggregatedItem]) -> FinancialSummary:
    """
    Build complete financial summary with category and grand totals.
    
    Combines category-level and overall totals into a single comprehensive
    financial summary for reporting and audit purposes.
    
    Args:
        aggregated_items: List of aggregated items
        
    Returns:
        Financial summary with category and grand totals
        
    Example:
        >>> financial_summary = build_financial_summary(aggregated_items)
        >>> len(financial_summary.category_totals)
        3
        >>> financial_summary.grand_totals.total_bill
        14873.80
    """
    category_totals = calculate_category_totals(aggregated_items)
    grand_totals = calculate_grand_totals(aggregated_items)
    
    logger.info(
        f"Built financial summary: "
        f"Bill=₹{grand_totals.total_bill:.2f}, "
        f"Allowed=₹{grand_totals.total_allowed:.2f}, "
        f"Extra=₹{grand_totals.total_extra:.2f}"
    )
    
    return FinancialSummary(
        category_totals=category_totals, grand_totals=grand_totals
    )


# =============================================================================
# Testing
# =============================================================================

if __name__ == "__main__":
    print("Financial aggregator module loaded successfully!")
    print("Use this module to calculate category and grand totals.")
