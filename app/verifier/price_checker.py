"""
Price Checker for the Hospital Bill Verifier.
Compares bill amounts against tie-up rates and determines verification status.

Pricing logic:
- unit: allowed_amount = rate × quantity
- service: allowed_amount = rate (fixed, quantity ignored)
- bundle: allowed_amount = rate (package price)

Status determination:
- GREEN: bill_amount <= allowed_amount
- RED: bill_amount > allowed_amount (overcharged)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

from app.verifier.models import ItemType, TieUpItem, VerificationStatus

logger = logging.getLogger(__name__)


@dataclass
class PriceCheckResult:
    """Result of a price comparison."""
    status: VerificationStatus
    bill_amount: float
    allowed_amount: float
    extra_amount: float  # 0 if GREEN, positive if RED
    
    @property
    def is_overcharged(self) -> bool:
        """Check if the item is overcharged."""
        return self.status == VerificationStatus.RED


def calculate_allowed_amount(
    tieup_item: TieUpItem,
    quantity: float = 1.0
) -> float:
    """
    Calculate the allowed amount based on tie-up rate and item type.
    
    Args:
        tieup_item: The matched tie-up item with rate and type
        quantity: Quantity from the bill (used only for 'unit' type)
        
    Returns:
        The maximum allowed amount
    """
    rate = tieup_item.rate
    item_type = tieup_item.type
    
    if item_type == ItemType.UNIT:
        # Per-unit pricing: rate × quantity
        allowed = rate * quantity
    elif item_type == ItemType.SERVICE:
        # Fixed service price (quantity doesn't matter)
        allowed = rate
    elif item_type == ItemType.BUNDLE:
        # Package/bundle price (quantity doesn't matter)
        allowed = rate
    else:
        # Default to unit pricing for unknown types
        logger.warning(f"Unknown item type '{item_type}', defaulting to unit pricing")
        allowed = rate * quantity
    
    return round(allowed, 2)


def check_price(
    bill_amount: float,
    tieup_item: Optional[TieUpItem],
    quantity: float = 1.0
) -> PriceCheckResult:
    """
    Compare bill amount against allowed amount and determine status.
    
    Args:
        bill_amount: Amount charged in the bill
        tieup_item: Matched tie-up item (None if no match)
        quantity: Quantity from the bill
        
    Returns:
        PriceCheckResult with status, amounts, and extra charge
    """
    bill_amount = round(bill_amount, 2)
    
    # No match = MISMATCH status
    if tieup_item is None:
        return PriceCheckResult(
            status=VerificationStatus.MISMATCH,
            bill_amount=bill_amount,
            allowed_amount=0.0,
            extra_amount=0.0
        )
    
    # Calculate allowed amount
    allowed_amount = calculate_allowed_amount(tieup_item, quantity)
    
    # Determine status
    if bill_amount <= allowed_amount:
        # Within allowed limit
        status = VerificationStatus.GREEN
        extra_amount = 0.0
    else:
        # Overcharged
        status = VerificationStatus.RED
        extra_amount = round(bill_amount - allowed_amount, 2)
    
    logger.debug(
        f"Price check: bill={bill_amount}, allowed={allowed_amount}, "
        f"extra={extra_amount}, status={status.value}"
    )
    
    return PriceCheckResult(
        status=status,
        bill_amount=bill_amount,
        allowed_amount=allowed_amount,
        extra_amount=extra_amount
    )


def create_mismatch_result(bill_amount: float) -> PriceCheckResult:
    """
    Create a MISMATCH result for items that couldn't be matched.
    
    Args:
        bill_amount: Amount charged in the bill
        
    Returns:
        PriceCheckResult with MISMATCH status
    """
    return PriceCheckResult(
        status=VerificationStatus.MISMATCH,
        bill_amount=round(bill_amount, 2),
        allowed_amount=0.0,
        extra_amount=0.0
    )
