"""
Medical Anchor Extraction for Hospital Bill Verifier.

Extracts domain-specific medical keywords to improve matching accuracy:
1. Dosage patterns: "5mg", "10ml", "500mcg"
2. Modality keywords: "MRI", "CT", "X-Ray", "Ultrasound"
3. Body part keywords: "brain", "chest", "abdomen", "cardiac"

These anchors provide medical context that pure semantic similarity might miss,
especially for items with similar meanings but different medical specifics.

Phase-2 Enhancement: Medical anchors contribute 25% to hybrid matching score.
"""

import re
from typing import Optional, Set, Tuple


# =============================================================================
# Medical Keyword Dictionaries
# =============================================================================

DOSAGE_PATTERNS = [
    r'\d+\s*mg',      # 5mg, 10 mg
    r'\d+\s*ml',      # 10ml, 5 ml
    r'\d+\s*mcg',     # 500mcg
    r'\d+\s*µg',      # 500µg (alternative)
    r'\d+\s*iu',      # 1000iu
    r'\d+\s*%',       # 5% (concentration)
    r'\d+\s*gm?',     # 10g, 10gm
    r'\d+\s*units?',  # 10 units
]

MODALITY_KEYWORDS = {
    'mri', 'ct', 'xray', 'x-ray', 'ultrasound', 'usg',
    'ecg', 'eeg', 'echo', 'endoscopy', 'colonoscopy',
    'mammography', 'pet', 'scan', 'sonography',
    'angiography', 'fluoroscopy', 'doppler',
    'echocardiography', 'electrocardiogram',
}

BODYPART_KEYWORDS = {
    'brain', 'head', 'chest', 'abdomen', 'cardiac', 'heart',
    'lung', 'liver', 'kidney', 'spine', 'knee', 'shoulder',
    'pelvis', 'neck', 'back', 'ankle', 'wrist', 'elbow',
    'hip', 'foot', 'hand', 'finger', 'toe', 'arm', 'leg',
    'stomach', 'intestine', 'pancreas', 'spleen', 'bladder',
    'cervical', 'thoracic', 'lumbar', 'sacral',
}


# =============================================================================
# Extraction Functions
# =============================================================================


def extract_dosage(text: str) -> Optional[str]:
    """
    Extract dosage pattern from text.
    
    Args:
        text: Input text (bill or tie-up item)
        
    Returns:
        Normalized dosage string or None
        
    Examples:
        >>> extract_dosage("NICORANDIL 5MG")
        '5mg'
        >>> extract_dosage("PARACETAMOL 500 MG")
        '500mg'
        >>> extract_dosage("INSULIN 10ML")
        '10ml'
        >>> extract_dosage("CONSULTATION")
        None
    """
    for pattern in DOSAGE_PATTERNS:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            # Normalize: remove spaces, convert to lowercase
            dosage = match.group(0).lower().replace(' ', '')
            # Normalize µg to mcg
            dosage = dosage.replace('µg', 'mcg')
            return dosage
    return None


def extract_modality(text: str) -> Optional[str]:
    """
    Extract modality keyword from text.
    
    Args:
        text: Input text (bill or tie-up item)
        
    Returns:
        Modality keyword or None
        
    Examples:
        >>> extract_modality("MRI BRAIN")
        'mri'
        >>> extract_modality("CT SCAN ABDOMEN")
        'ct'
        >>> extract_modality("X-RAY CHEST")
        'x-ray'
        >>> extract_modality("CONSULTATION")
        None
    """
    text_lower = text.lower()
    
    # Check for each modality keyword
    for modality in MODALITY_KEYWORDS:
        # Use word boundary to avoid partial matches
        if re.search(r'\b' + re.escape(modality) + r'\b', text_lower):
            return modality
    
    return None


def extract_bodypart(text: str) -> Optional[str]:
    """
    Extract body part keyword from text.
    
    Args:
        text: Input text (bill or tie-up item)
        
    Returns:
        Body part keyword or None
        
    Examples:
        >>> extract_bodypart("MRI BRAIN")
        'brain'
        >>> extract_bodypart("CT SCAN ABDOMEN")
        'abdomen'
        >>> extract_bodypart("CARDIAC ECHO")
        'cardiac'
        >>> extract_bodypart("CONSULTATION")
        None
    """
    text_lower = text.lower()
    
    # Check for each body part keyword
    for bodypart in BODYPART_KEYWORDS:
        # Use word boundary to avoid partial matches
        if re.search(r'\b' + re.escape(bodypart) + r'\b', text_lower):
            return bodypart
    
    return None


# =============================================================================
# Medical Anchor Scoring
# =============================================================================


def calculate_medical_anchor_score(
    bill_item: str, tieup_item: str
) -> Tuple[float, dict]:
    """
    Calculate medical anchor score based on domain-specific matches.
    
    Scoring:
    - Dosage match: +0.4 (critical for medicines)
    - Modality match: +0.3 (important for diagnostics)
    - Body part match: +0.3 (important for diagnostics)
    
    Maximum score: 1.0 (all three match)
    
    Args:
        bill_item: Normalized bill item text
        tieup_item: Normalized tie-up item text
        
    Returns:
        Tuple of (score, breakdown_dict)
        
    Examples:
        >>> score, breakdown = calculate_medical_anchor_score("mri brain 5mg", "mri brain 5mg")
        >>> score
        1.0
        >>> breakdown['dosage_match']
        True
        
        >>> score, breakdown = calculate_medical_anchor_score("mri brain", "mri brain")
        >>> score
        0.6
        >>> breakdown['modality_match']
        True
        >>> breakdown['bodypart_match']
        True
    """
    breakdown = {
        'dosage_match': False,
        'modality_match': False,
        'bodypart_match': False,
        'score': 0.0,
    }
    
    score = 0.0
    
    # Dosage match (+0.4)
    bill_dosage = extract_dosage(bill_item)
    tieup_dosage = extract_dosage(tieup_item)
    if bill_dosage and tieup_dosage and bill_dosage == tieup_dosage:
        score += 0.4
        breakdown['dosage_match'] = True
    
    # Modality match (+0.3)
    bill_modality = extract_modality(bill_item)
    tieup_modality = extract_modality(tieup_item)
    if bill_modality and tieup_modality and bill_modality == tieup_modality:
        score += 0.3
        breakdown['modality_match'] = True
    
    # Body part match (+0.3)
    bill_bodypart = extract_bodypart(bill_item)
    tieup_bodypart = extract_bodypart(tieup_item)
    if bill_bodypart and tieup_bodypart and bill_bodypart == tieup_bodypart:
        score += 0.3
        breakdown['bodypart_match'] = True
    
    breakdown['score'] = min(score, 1.0)  # Cap at 1.0
    return breakdown['score'], breakdown


# =============================================================================
# Testing
# =============================================================================

if __name__ == "__main__":
    # Test cases
    test_cases = [
        # Dosage extraction
        ("NICORANDIL 5MG", "5mg"),
        ("PARACETAMOL 500 MG", "500mg"),
        ("INSULIN 10ML", "10ml"),
        ("CONSULTATION", None),
        
        # Modality extraction
        ("MRI BRAIN", "mri"),
        ("CT SCAN ABDOMEN", "ct"),
        ("X-RAY CHEST", "x-ray"),
        ("CONSULTATION", None),
        
        # Body part extraction
        ("MRI BRAIN", "brain"),
        ("CT SCAN ABDOMEN", "abdomen"),
        ("CARDIAC ECHO", "cardiac"),
        ("CONSULTATION", None),
    ]
    
    print("Medical Anchor Extraction Test Cases:")
    print("=" * 80)
    
    for text, expected in test_cases[:4]:
        result = extract_dosage(text)
        status = "✅" if result == expected else "❌"
        print(f"{status} Dosage: '{text}' → {result} (expected {expected})")
    
    print()
    
    for text, expected in test_cases[4:8]:
        result = extract_modality(text)
        status = "✅" if result == expected else "❌"
        print(f"{status} Modality: '{text}' → {result} (expected {expected})")
    
    print()
    
    for text, expected in test_cases[8:]:
        result = extract_bodypart(text)
        status = "✅" if result == expected else "❌"
        print(f"{status} Body Part: '{text}' → {result} (expected {expected})")
    
    print("\n" + "=" * 80)
    print("Medical Anchor Scoring Test:")
    print("=" * 80)
    
    # Test scoring
    test_pairs = [
        ("mri brain 5mg", "mri brain 5mg", 1.0),
        ("mri brain", "mri brain", 0.6),
        ("nicorandil 5mg", "nicorandil 5mg", 0.4),
        ("consultation", "consultation", 0.0),
    ]
    
    for bill, tieup, expected_score in test_pairs:
        score, breakdown = calculate_medical_anchor_score(bill, tieup)
        status = "✅" if abs(score - expected_score) < 0.01 else "❌"
        print(f"{status} '{bill}' vs '{tieup}' → {score:.1f} (expected {expected_score:.1f})")
        print(f"    Breakdown: {breakdown}")
