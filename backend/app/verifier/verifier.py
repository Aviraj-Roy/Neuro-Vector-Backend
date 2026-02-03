"""
Bill Verifier Service - Main orchestration module.
Combines semantic matching and price checking to verify hospital bills.

Processing Flow:
1. Fetch bill JSON from MongoDB
2. Match hospital semantically → pick best tie-up rate sheet
3. For each category in bill:
   a. Match category semantically (threshold 0.70)
   b. If category match fails → mark all items as MISMATCH
   c. For each item in category:
      - Match item semantically (threshold 0.85)
      - Compare price against tie-up rate
      - Determine GREEN/RED/MISMATCH status
4. Return structured verification response
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.verifier.matcher import (
    CATEGORY_SIMILARITY_THRESHOLD,
    ITEM_SIMILARITY_THRESHOLD,
    SemanticMatcher,
    get_matcher,
)
from app.verifier.models import (
    BillCategory,
    BillInput,
    BillItem,
    CategoryVerificationResult,
    ItemVerificationResult,
    TieUpRateSheet,
    VerificationResponse,
    VerificationStatus,
)
from app.verifier.price_checker import check_price, create_mismatch_result

logger = logging.getLogger(__name__)


# =============================================================================
# Tie-Up Rate Sheet Loader
# =============================================================================

def load_tieup_from_file(file_path: str) -> TieUpRateSheet:
    """
    Load a single tie-up rate sheet from a JSON file.
    
    Args:
        file_path: Path to the JSON file
        
    Returns:
        TieUpRateSheet object
    """
    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return TieUpRateSheet(**data)


def load_all_tieups(directory: str) -> List[TieUpRateSheet]:
    """
    Load all tie-up rate sheets from a directory.
    
    Args:
        directory: Path to directory containing JSON files
        
    Returns:
        List of TieUpRateSheet objects
    """
    rate_sheets = []
    dir_path = Path(directory)
    
    if not dir_path.exists():
        logger.warning(f"Tie-up directory does not exist: {directory}")
        return rate_sheets
    
    for file_path in dir_path.glob("*.json"):
        try:
            rate_sheet = load_tieup_from_file(str(file_path))
            rate_sheets.append(rate_sheet)
            logger.info(f"Loaded tie-up rate sheet: {rate_sheet.hospital_name}")
        except Exception as e:
            logger.error(f"Failed to load {file_path}: {e}")
    
    return rate_sheets


# =============================================================================
# Bill Verifier Service
# =============================================================================

class BillVerifier:
    """
    Main bill verification service.
    Orchestrates semantic matching and price checking.
    """
    
    def __init__(
        self,
        matcher: Optional[SemanticMatcher] = None,
        tieup_directory: Optional[str] = None
    ):
        """
        Initialize the bill verifier.
        
        Args:
            matcher: SemanticMatcher instance (uses global if None)
            tieup_directory: Directory containing tie-up JSON files
        """
        self.matcher = matcher or get_matcher()
        
        # Use config-based path resolution
        from app.config import TIEUP_DIR
        self.tieup_directory = tieup_directory or os.getenv(
            "TIEUP_DATA_DIR", 
            str(TIEUP_DIR)
        )
        self._initialized = False
    
    def initialize(self, rate_sheets: Optional[List[TieUpRateSheet]] = None):
        """
        Initialize the verifier with tie-up rate sheets.
        
        Args:
            rate_sheets: List of rate sheets (loads from directory if None)
        """
        if rate_sheets is None:
            rate_sheets = load_all_tieups(self.tieup_directory)
        
        if not rate_sheets:
            logger.warning("No tie-up rate sheets loaded!")
            return
        
        self.matcher.index_rate_sheets(rate_sheets)
        self._initialized = True
        logger.info(f"BillVerifier initialized with {len(rate_sheets)} rate sheets")
    
    def verify_bill(self, bill: BillInput) -> VerificationResponse:
        """
        Verify a hospital bill against tie-up rates.
        
        Args:
            bill: BillInput object (from MongoDB)
            
        Returns:
            VerificationResponse with all verification results
        """
        if not self._initialized:
            self.initialize()
        
        logger.info(f"Verifying bill from hospital: {bill.hospital_name}")
        
        # Step 1: Match hospital
        hospital_match = self.matcher.match_hospital(bill.hospital_name)
        
        if not hospital_match.is_match or hospital_match.rate_sheet is None:
            # No matching hospital - all items are MISMATCH
            logger.warning(f"No matching hospital found for: {bill.hospital_name}")
            return self._create_all_mismatch_response(bill)
        
        matched_hospital = hospital_match.matched_text
        rate_sheet = hospital_match.rate_sheet
        
        logger.info(
            f"Hospital matched: '{bill.hospital_name}' -> '{matched_hospital}' "
            f"(similarity={hospital_match.similarity:.4f})"
        )
        
        # Initialize response
        response = VerificationResponse(
            hospital=bill.hospital_name,
            matched_hospital=matched_hospital,
            hospital_similarity=hospital_match.similarity,
        )
        
        # Step 2: Process each category
        for bill_category in bill.categories:
            category_result = self._verify_category(
                bill_category=bill_category,
                hospital_name=matched_hospital,
            )
            response.results.append(category_result)
            
            # Update summary statistics
            for item_result in category_result.items:
                response.total_bill_amount += item_result.bill_amount
                response.total_allowed_amount += item_result.allowed_amount
                response.total_extra_amount += item_result.extra_amount
                
                if item_result.status == VerificationStatus.GREEN:
                    response.green_count += 1
                elif item_result.status == VerificationStatus.RED:
                    response.red_count += 1
                else:
                    response.mismatch_count += 1
        
        logger.info(
            f"Verification complete: GREEN={response.green_count}, "
            f"RED={response.red_count}, MISMATCH={response.mismatch_count}"
        )
        
        return response
    
    def _verify_category(
        self,
        bill_category: BillCategory,
        hospital_name: str,
    ) -> CategoryVerificationResult:
        """
        Verify all items in a category.
        
        Args:
            bill_category: Category from the bill
            hospital_name: Matched hospital name
            
        Returns:
            CategoryVerificationResult
        """
        # Match category
        category_match = self.matcher.match_category(
            category_name=bill_category.category_name,
            hospital_name=hospital_name,
            threshold=CATEGORY_SIMILARITY_THRESHOLD,
        )
        
        result = CategoryVerificationResult(
            category=bill_category.category_name,
            matched_category=category_match.matched_text,
            category_similarity=category_match.similarity,
        )
        
        # If category doesn't match threshold, all items are MISMATCH
        if not category_match.is_match:
            logger.warning(
                f"Category mismatch: '{bill_category.category_name}' "
                f"(best similarity={category_match.similarity:.4f} < {CATEGORY_SIMILARITY_THRESHOLD})"
            )
            for bill_item in bill_category.items:
                item_result = self._create_mismatch_item_result(bill_item)
                result.items.append(item_result)
            return result
        
        # Process each item in the category
        for bill_item in bill_category.items:
            item_result = self._verify_item(
                bill_item=bill_item,
                hospital_name=hospital_name,
                category_name=category_match.matched_text,
            )
            result.items.append(item_result)
        
        return result
    
    def _verify_item(
        self,
        bill_item: BillItem,
        hospital_name: str,
        category_name: str,
    ) -> ItemVerificationResult:
        """
        Verify a single item.
        
        Args:
            bill_item: Item from the bill
            hospital_name: Matched hospital name
            category_name: Matched category name
            
        Returns:
            ItemVerificationResult
        """
        # Match item
        item_match = self.matcher.match_item(
            item_name=bill_item.item_name,
            hospital_name=hospital_name,
            category_name=category_name,
            threshold=ITEM_SIMILARITY_THRESHOLD,
        )
        
        # Check price
        if item_match.is_match and item_match.item is not None:
            price_result = check_price(
                bill_amount=bill_item.amount,
                tieup_item=item_match.item,
                quantity=bill_item.quantity,
            )
            
            return ItemVerificationResult(
                bill_item=bill_item.item_name,
                matched_item=item_match.matched_text,
                status=price_result.status,
                bill_amount=price_result.bill_amount,
                allowed_amount=price_result.allowed_amount,
                extra_amount=price_result.extra_amount,
                similarity_score=item_match.similarity,
            )
        else:
            # Item mismatch
            logger.debug(
                f"Item mismatch: '{bill_item.item_name}' "
                f"(best similarity={item_match.similarity:.4f} < {ITEM_SIMILARITY_THRESHOLD})"
            )
            return self._create_mismatch_item_result(bill_item, item_match.similarity)
    
    def _create_mismatch_item_result(
        self,
        bill_item: BillItem,
        similarity: float = 0.0,
    ) -> ItemVerificationResult:
        """Create a MISMATCH result for an item."""
        return ItemVerificationResult(
            bill_item=bill_item.item_name,
            matched_item=None,
            status=VerificationStatus.MISMATCH,
            bill_amount=bill_item.amount,
            allowed_amount=0.0,
            extra_amount=0.0,
            similarity_score=similarity,
        )
    
    def _create_all_mismatch_response(self, bill: BillInput) -> VerificationResponse:
        """Create a response where everything is MISMATCH (no hospital match)."""
        response = VerificationResponse(
            hospital=bill.hospital_name,
            matched_hospital=None,
            hospital_similarity=0.0,
        )
        
        for bill_category in bill.categories:
            category_result = CategoryVerificationResult(
                category=bill_category.category_name,
                matched_category=None,
                category_similarity=0.0,
            )
            
            for bill_item in bill_category.items:
                item_result = self._create_mismatch_item_result(bill_item)
                category_result.items.append(item_result)
                response.total_bill_amount += bill_item.amount
                response.mismatch_count += 1
            
            response.results.append(category_result)
        
        return response


# =============================================================================
# Module-level singleton
# =============================================================================

_verifier: Optional[BillVerifier] = None


def get_verifier() -> BillVerifier:
    """Get or create the global bill verifier instance."""
    global _verifier
    if _verifier is None:
        _verifier = BillVerifier()
    return _verifier
