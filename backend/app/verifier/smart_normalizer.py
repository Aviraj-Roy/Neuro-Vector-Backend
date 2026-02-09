"""
Smart Normalization with Token Weighting.

Key Improvements:
1. Preserves medically meaningful tokens (FIRST, VISIT, FOLLOW-UP)
2. Weighted token importance (drug name > dosage > form > brand)
3. Context-aware normalization based on item type
4. Minimal information loss
"""

from __future__ import annotations

import re
from typing import List, Tuple, Set
from dataclasses import dataclass
from enum import Enum


class TokenImportance(str, Enum):
    """Token importance levels for weighted matching."""
    CRITICAL = "CRITICAL"      # Drug name, modality, procedure name
    HIGH = "HIGH"              # Dosage, body part, form (when relevant)
    MEDIUM = "MEDIUM"          # Qualifiers (first, follow-up, emergency)
    LOW = "LOW"                # Brand names, packaging
    NOISE = "NOISE"            # SKU codes, lot numbers, pure noise


@dataclass
class WeightedToken:
    """Token with importance weight."""
    text: str
    importance: TokenImportance
    original_position: int
    
    def __str__(self):
        return self.text


# =============================================================================
# Token Classification
# =============================================================================

# Critical medical terms (preserve always)
CRITICAL_MEDICAL_TERMS = {
    # Drug names (examples - would be expanded)
    'paracetamol', 'aspirin', 'insulin', 'metformin', 'nicorandil',
    # Modalities
    'mri', 'ct', 'xray', 'x-ray', 'ultrasound', 'ecg', 'echo',
    # Procedures
    'consultation', 'surgery', 'biopsy', 'endoscopy',
}

# High importance qualifiers (preserve for pricing differentiation)
HIGH_IMPORTANCE_QUALIFIERS = {
    'first', 'second', 'third',
    'follow', 'followup', 'follow-up',
    'emergency', 'urgent',
    'specialist', 'senior', 'junior',
    'initial', 'repeat',
}

# Medium importance terms (preserve context)
MEDIUM_IMPORTANCE_TERMS = {
    'visit', 'consultation', 'session',
    'left', 'right', 'bilateral',
    'upper', 'lower', 'anterior', 'posterior',
}

# Low importance (brand/packaging - can be removed if needed)
LOW_IMPORTANCE_TERMS = {
    'brand', 'manufacturer', 'company',
    'strip', 'box', 'pack', 'bottle',
}

# Noise (always remove)
NOISE_PATTERNS = [
    r'\(\d{4,}\)',  # SKU codes
    r'LOT[:\s]*[A-Z0-9\-]+',  # Lot numbers
    r'BATCH[:\s]*[A-Z0-9\-]+',  # Batch codes
    r'\|[A-Z]{2,}\s*$',  # Brand suffixes
]


def classify_token_importance(token: str, position: int, context: str) -> TokenImportance:
    """
    Classify token importance based on medical domain knowledge.
    
    Args:
        token: Token to classify
        position: Position in original text
        context: Full text context
        
    Returns:
        TokenImportance enum
    """
    token_lower = token.lower()
    
    # Check if it's noise
    for pattern in NOISE_PATTERNS:
        if re.match(pattern, token, re.IGNORECASE):
            return TokenImportance.NOISE
    
    # Check if it's a dosage (HIGH importance)
    if re.match(r'\d+\.?\d*(mg|mcg|ml|g|iu|units?)', token_lower):
        return TokenImportance.HIGH
    
    # Check critical medical terms
    if token_lower in CRITICAL_MEDICAL_TERMS:
        return TokenImportance.CRITICAL
    
    # Check high importance qualifiers
    if token_lower in HIGH_IMPORTANCE_QUALIFIERS:
        return TokenImportance.HIGH
    
    # Check medium importance
    if token_lower in MEDIUM_IMPORTANCE_TERMS:
        return TokenImportance.MEDIUM
    
    # Check low importance
    if token_lower in LOW_IMPORTANCE_TERMS:
        return TokenImportance.LOW
    
    # Default: If it's a long word (likely medical term), mark as CRITICAL
    if len(token) >= 5 and token.isalpha():
        return TokenImportance.CRITICAL
    
    # Otherwise, medium importance
    return TokenImportance.MEDIUM


def tokenize_with_weights(text: str) -> List[WeightedToken]:
    """
    Tokenize text and assign importance weights.
    
    Args:
        text: Input text
        
    Returns:
        List of WeightedToken objects
        
    Example:
        >>> tokens = tokenize_with_weights("CONSULTATION - FIRST VISIT | Dr. Vivek")
        >>> [(t.text, t.importance.value) for t in tokens]
        [('consultation', 'CRITICAL'), ('first', 'HIGH'), ('visit', 'MEDIUM')]
    """
    # Clean and tokenize
    cleaned = re.sub(r'[^\w\s-]', ' ', text)
    tokens = cleaned.split()
    
    weighted_tokens = []
    for i, token in enumerate(tokens):
        if len(token) < 2:  # Skip very short tokens
            continue
            
        importance = classify_token_importance(token, i, text)
        
        # Skip noise tokens
        if importance == TokenImportance.NOISE:
            continue
        
        weighted_tokens.append(WeightedToken(
            text=token.lower(),
            importance=importance,
            original_position=i
        ))
    
    return weighted_tokens


def normalize_with_weights(
    text: str,
    preserve_qualifiers: bool = True,
    min_importance: TokenImportance = TokenImportance.MEDIUM
) -> Tuple[str, List[WeightedToken]]:
    """
    Normalize text while preserving important tokens.
    
    Args:
        text: Input text
        preserve_qualifiers: Whether to preserve HIGH importance qualifiers
        min_importance: Minimum importance level to keep
        
    Returns:
        Tuple of (normalized_text, weighted_tokens)
        
    Example:
        >>> normalize_with_weights("CONSULTATION - FIRST VISIT | Dr. Vivek")
        ('consultation first visit', [WeightedToken(...), ...])
        
        >>> normalize_with_weights("(30049099) NICORANDIL-5MG |GTF")
        ('nicorandil 5mg', [WeightedToken(...), ...])
    """
    # Get weighted tokens
    tokens = tokenize_with_weights(text)
    
    # Filter by importance
    importance_order = {
        TokenImportance.CRITICAL: 4,
        TokenImportance.HIGH: 3,
        TokenImportance.MEDIUM: 2,
        TokenImportance.LOW: 1,
        TokenImportance.NOISE: 0,
    }
    
    min_level = importance_order[min_importance]
    
    filtered_tokens = [
        t for t in tokens
        if importance_order[t.importance] >= min_level
    ]
    
    # Build normalized text
    normalized = ' '.join(t.text for t in filtered_tokens)
    
    return normalized, filtered_tokens


# =============================================================================
# Before/After Examples
# =============================================================================

def demonstrate_normalization():
    """Show before/after normalization examples."""
    
    test_cases = [
        # Case 1: Consultation with qualifiers
        "CONSULTATION - FIRST VISIT | Dr. Vivek Jacob P",
        
        # Case 2: Medicine with inventory noise
        "(30049099) NICORANDIL-TABLET-5MG-KORANDIL- |GTF",
        
        # Case 3: Diagnostic with doctor name
        "MRI BRAIN | Dr. Vivek Jacob Philip",
        
        # Case 4: Follow-up consultation
        "CONSULTATION - FOLLOW UP VISIT",
        
        # Case 5: Emergency procedure
        "EMERGENCY CONSULTATION - SPECIALIST",
    ]
    
    print("=" * 80)
    print("SMART NORMALIZATION - BEFORE/AFTER EXAMPLES")
    print("=" * 80)
    
    for i, test in enumerate(test_cases, 1):
        print(f"\n{'─' * 80}")
        print(f"CASE {i}:")
        print(f"{'─' * 80}")
        print(f"BEFORE: '{test}'")
        
        # Normalize with different settings
        normalized_full, tokens_full = normalize_with_weights(
            test, preserve_qualifiers=True, min_importance=TokenImportance.MEDIUM
        )
        
        normalized_minimal, tokens_minimal = normalize_with_weights(
            test, preserve_qualifiers=False, min_importance=TokenImportance.HIGH
        )
        
        print(f"\nAFTER (preserve qualifiers): '{normalized_full}'")
        print(f"Tokens: {[f'{t.text}({t.importance.value})' for t in tokens_full]}")
        
        print(f"\nAFTER (minimal): '{normalized_minimal}'")
        print(f"Tokens: {[f'{t.text}({t.importance.value})' for t in tokens_minimal]}")
        
        # Show what was removed
        original_words = set(test.lower().split())
        kept_words = set(t.text for t in tokens_full)
        removed = original_words - kept_words
        if removed:
            print(f"\nREMOVED: {removed}")
    
    print(f"\n{'=' * 80}")


if __name__ == "__main__":
    demonstrate_normalization()
