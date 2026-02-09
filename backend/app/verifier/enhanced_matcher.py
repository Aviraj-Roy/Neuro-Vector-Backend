"""
Enhanced Matching Engine with Layered Architecture.

Implements the 6-layer matching strategy:
0. Pre-filtering (artifacts, packages)
1. Medical core extraction
2. Hard constraint validation
3. Semantic matching with category-specific thresholds
4. Hybrid re-ranking
5. Confidence calibration
6. Failure reason determination
"""

from __future__ import annotations

import logging
from typing import Optional, List, Tuple, Dict
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)


# =============================================================================
# Configuration
# =============================================================================

@dataclass
class CategoryMatchingConfig:
    """Matching configuration for a specific category."""
    semantic_threshold: float
    require_dosage_match: bool = False
    require_form_awareness: bool = False
    require_modality_match: bool = False
    require_bodypart_match: bool = False
    allow_partial_match: bool = False
    hard_boundaries: List[str] = None
    
    def __post_init__(self):
        if self.hard_boundaries is None:
            self.hard_boundaries = []


# Category-specific configurations
CATEGORY_CONFIGS = {
    "medicines": CategoryMatchingConfig(
        semantic_threshold=0.75,
        require_dosage_match=True,
        require_form_awareness=True,
        hard_boundaries=["diagnostics", "procedures", "radiology", "laboratory"]
    ),
    "pharmacy": CategoryMatchingConfig(
        semantic_threshold=0.75,
        require_dosage_match=True,
        require_form_awareness=True,
        hard_boundaries=["diagnostics", "procedures"]
    ),
    "diagnostics": CategoryMatchingConfig(
        semantic_threshold=0.70,
        require_modality_match=True,
        require_bodypart_match=True,
        hard_boundaries=["medicines", "pharmacy"]
    ),
    "radiology": CategoryMatchingConfig(
        semantic_threshold=0.70,
        require_modality_match=True,
        require_bodypart_match=True,
        hard_boundaries=["medicines", "pharmacy"]
    ),
    "laboratory": CategoryMatchingConfig(
        semantic_threshold=0.70,
        hard_boundaries=["medicines", "pharmacy"]
    ),
    "procedures": CategoryMatchingConfig(
        semantic_threshold=0.65,
        allow_partial_match=True,
        hard_boundaries=["medicines", "pharmacy"]
    ),
    "consultation": CategoryMatchingConfig(
        semantic_threshold=0.65,
        allow_partial_match=True,
        hard_boundaries=["medicines", "pharmacy"]
    ),
    "surgery": CategoryMatchingConfig(
        semantic_threshold=0.70,
        hard_boundaries=["medicines", "pharmacy", "diagnostics"]
    ),
    "implants": CategoryMatchingConfig(
        semantic_threshold=0.75,
        hard_boundaries=["medicines", "pharmacy", "diagnostics"]
    ),
    "consumables": CategoryMatchingConfig(
        semantic_threshold=0.70,
        hard_boundaries=[]  # Consumables can be flexible
    ),
}

# Default config for unknown categories
DEFAULT_CONFIG = CategoryMatchingConfig(
    semantic_threshold=0.70,
    allow_partial_match=True
)


def get_category_config(category_name: str) -> CategoryMatchingConfig:
    """
    Get matching configuration for a category.
    
    Args:
        category_name: Category name
        
    Returns:
        CategoryMatchingConfig
    """
    category_lower = category_name.lower().strip()
    
    # Direct match
    if category_lower in CATEGORY_CONFIGS:
        return CATEGORY_CONFIGS[category_lower]
    
    # Fuzzy match (contains)
    for key, config in CATEGORY_CONFIGS.items():
        if key in category_lower or category_lower in key:
            return config
    
    # Default
    return DEFAULT_CONFIG


# =============================================================================
# Layer 0: Pre-Filtering
# =============================================================================

def prefilter_item(item_name: str) -> Tuple[bool, Optional[str]]:
    """
    Pre-filter items that should not enter semantic matching.
    
    Returns:
        Tuple of (should_skip, reason)
        
    Examples:
        >>> prefilter_item("For queries call 1800-XXX-XXXX")
        (True, "ARTIFACT")
        
        >>> prefilter_item("HEALTH CHECKUP PACKAGE")
        (True, "PACKAGE")
        
        >>> prefilter_item("MRI BRAIN")
        (False, None)
    """
    from app.verifier.artifact_detector import is_artifact
    
    # Check if artifact
    if is_artifact(item_name):
        return True, "ARTIFACT"
    
    # Check if package/bundle
    package_keywords = ['package', 'pkg', 'bundle', 'combo', 'plan']
    item_lower = item_name.lower()
    if any(keyword in item_lower for keyword in package_keywords):
        return True, "PACKAGE"
    
    # Not filtered
    return False, None


# =============================================================================
# Layer 2: Hard Constraint Validation
# =============================================================================

def validate_hard_constraints(
    bill_metadata: Dict,
    tieup_metadata: Dict,
    bill_category: str,
    tieup_category: str,
    config: CategoryMatchingConfig
) -> Tuple[bool, Optional[str]]:
    """
    Validate hard constraints before semantic matching.
    
    Args:
        bill_metadata: Extracted metadata from bill item
        tieup_metadata: Extracted metadata from tie-up item
        bill_category: Bill category
        tieup_category: Tie-up category
        config: Category matching configuration
        
    Returns:
        Tuple of (valid, rejection_reason)
    """
    # Check category boundaries
    from app.verifier.category_enforcer import check_category_boundary
    
    allowed, reason = check_category_boundary(bill_category, tieup_category, 1.0)
    if not allowed:
        return False, f"CATEGORY_BOUNDARY: {reason}"
    
    # Check dosage match (if required)
    if config.require_dosage_match:
        bill_dosage = bill_metadata.get('dosage')
        tieup_dosage = tieup_metadata.get('dosage')
        
        if bill_dosage and tieup_dosage:
            # Normalize dosages for comparison
            from app.verifier.medical_core_extractor_v2 import MedicalCoreResult
            
            bill_norm = MedicalCoreResult._normalize_dosage(bill_dosage)
            tieup_norm = MedicalCoreResult._normalize_dosage(tieup_dosage)
            
            if bill_norm != tieup_norm:
                return False, f"DOSAGE_MISMATCH: {bill_dosage} ≠ {tieup_dosage}"
    
    # Check form awareness (if required)
    if config.require_form_awareness:
        bill_form = bill_metadata.get('form')
        tieup_form = tieup_metadata.get('form')
        
        # Only enforce if both have forms
        if bill_form and tieup_form:
            # For certain drugs (insulin, epinephrine), form matters
            critical_form_drugs = ['insulin', 'epinephrine', 'adrenaline']
            bill_core = bill_metadata.get('core_text', '').lower()
            
            is_critical = any(drug in bill_core for drug in critical_form_drugs)
            
            if is_critical and bill_form != tieup_form:
                return False, f"FORM_MISMATCH: {bill_form} ≠ {tieup_form} (critical drug)"
    
    # Check modality match (if required)
    if config.require_modality_match:
        bill_modality = bill_metadata.get('modality')
        tieup_modality = tieup_metadata.get('modality')
        
        if bill_modality and tieup_modality and bill_modality != tieup_modality:
            return False, f"MODALITY_MISMATCH: {bill_modality} ≠ {tieup_modality}"
    
    # Check body part match (if required)
    if config.require_bodypart_match:
        bill_bodypart = bill_metadata.get('body_part')
        tieup_bodypart = tieup_metadata.get('body_part')
        
        if bill_bodypart and tieup_bodypart and bill_bodypart != tieup_bodypart:
            return False, f"BODYPART_MISMATCH: {bill_bodypart} ≠ {tieup_bodypart}"
    
    # All constraints passed
    return True, None


# =============================================================================
# Layer 4: Hybrid Re-Ranking
# =============================================================================

def calculate_hybrid_score_v3(
    bill_text: str,
    tieup_text: str,
    semantic_similarity: float,
    bill_metadata: Dict,
    tieup_metadata: Dict,
    category: str
) -> Tuple[float, Dict]:
    """
    Calculate hybrid score with medical domain knowledge.
    
    Weighting:
    - Semantic similarity: 50%
    - Medical anchors: 30% (dosage, modality, body part)
    - Token overlap: 20%
    
    Args:
        bill_text: Normalized bill item text
        tieup_text: Normalized tie-up item text
        semantic_similarity: Embedding similarity score
        bill_metadata: Bill item metadata
        tieup_metadata: Tie-up item metadata
        category: Category name
        
    Returns:
        Tuple of (final_score, breakdown_dict)
    """
    from app.verifier.partial_matcher import calculate_token_overlap
    from app.verifier.medical_anchors import calculate_medical_anchor_score
    
    # Calculate components
    token_overlap = calculate_token_overlap(bill_text, tieup_text)
    medical_score, medical_breakdown = calculate_medical_anchor_score(bill_text, tieup_text)
    
    # Weighted combination
    final_score = (
        0.50 * semantic_similarity +
        0.30 * medical_score +
        0.20 * token_overlap
    )
    
    breakdown = {
        'semantic': semantic_similarity,
        'medical_anchors': medical_score,
        'token_overlap': token_overlap,
        'final_score': final_score,
        'weights': {'semantic': 0.50, 'medical': 0.30, 'token': 0.20},
        'medical_breakdown': medical_breakdown
    }
    
    return final_score, breakdown


# =============================================================================
# Layer 5: Confidence Calibration
# =============================================================================

class MatchDecision(str, Enum):
    """Match decision after confidence calibration."""
    AUTO_MATCH = "AUTO_MATCH"
    LLM_VERIFY = "LLM_VERIFY"
    REJECT = "REJECT"


def calibrate_confidence(
    final_score: float,
    category: str,
    breakdown: Dict
) -> Tuple[MatchDecision, float]:
    """
    Calibrate confidence and make match decision.
    
    Args:
        final_score: Hybrid score
        category: Category name
        breakdown: Score breakdown
        
    Returns:
        Tuple of (decision, calibrated_confidence)
    """
    config = get_category_config(category)
    
    # High confidence threshold
    HIGH_CONFIDENCE = 0.80
    
    # Category-specific threshold
    category_threshold = config.semantic_threshold
    
    # LLM verification threshold (10% below category threshold)
    llm_threshold = category_threshold - 0.10
    
    # Decision logic
    if final_score >= HIGH_CONFIDENCE:
        return MatchDecision.AUTO_MATCH, final_score
    elif final_score >= category_threshold:
        # Check if medical anchors are strong
        medical_score = breakdown.get('medical_anchors', 0.0)
        if medical_score >= 0.7:
            # Strong medical match, auto-accept
            return MatchDecision.AUTO_MATCH, final_score
        else:
            # Borderline, use LLM
            return MatchDecision.LLM_VERIFY, final_score
    elif final_score >= llm_threshold:
        # Borderline case, use LLM
        return MatchDecision.LLM_VERIFY, final_score
    else:
        # Low confidence, reject
        return MatchDecision.REJECT, final_score


# =============================================================================
# Testing
# =============================================================================

if __name__ == "__main__":
    print("Enhanced Matching Engine - Configuration Test")
    print("=" * 80)
    
    # Test category configs
    test_categories = ["Medicines", "Diagnostics", "Procedures", "Unknown Category"]
    
    for cat in test_categories:
        config = get_category_config(cat)
        print(f"\nCategory: {cat}")
        print(f"  Semantic Threshold: {config.semantic_threshold}")
        print(f"  Require Dosage Match: {config.require_dosage_match}")
        print(f"  Require Modality Match: {config.require_modality_match}")
        print(f"  Hard Boundaries: {config.hard_boundaries}")
    
    print("\n" + "=" * 80)
    
    # Test pre-filtering
    print("\nPre-Filtering Tests:")
    test_items = [
        "MRI BRAIN",
        "For queries call 1800-XXX-XXXX",
        "HEALTH CHECKUP PACKAGE",
        "PARACETAMOL 500MG",
    ]
    
    for item in test_items:
        should_skip, reason = prefilter_item(item)
        status = "SKIP" if should_skip else "PROCESS"
        print(f"  {status}: '{item}' {f'({reason})' if reason else ''}")
    
    print("\n" + "=" * 80)
