"""
OCR Artifact Detector for Hospital Bill Verifier.

Detects and filters OCR artifacts, administrative metadata, and non-medical
content that should be ignored during verification.

Examples of artifacts:
- Page numbers: "Page 1 of 2"
- Contact info: "Ph: +91-9876543210", "info@hospital.com"
- App prompts: "Download our app"
- Bill metadata: "Bill No: 12345", "Date: 01/01/2024"
"""

import re
from typing import List


# =============================================================================
# Artifact Detection Patterns
# =============================================================================

IGNORE_PATTERNS: List[str] = [
    # Page numbers
    r'page\s+\d+\s+of\s+\d+',
    r'page\s+\d+',
    
    # Phone numbers (various formats)
    r'\+?\d{2,3}[-.\s]?\d{10}',
    r'\(\d{3}\)\s*\d{3}[-.\s]?\d{4}',
    r'\d{3}[-.\s]?\d{3}[-.\s]?\d{4}',
    
    # Email addresses
    r'[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}',
    
    # App download prompts
    r'download\s+(our\s+)?app',
    r'scan\s+qr\s+code',
    r'available\s+on\s+(play\s+store|app\s+store)',
    
    # Bill metadata
    r'bill\s+(no|number|#)',
    r'invoice\s+(no|number|#)',
    r'receipt\s+(no|number|#)',
    
    # Date headers
    r'date[:\s]+\d{2}[/-]\d{2}',
    r'\d{2}[/-]\d{2}[/-]\d{2,4}',
    
    # Website URLs
    r'www\.[a-z0-9.-]+\.[a-z]{2,}',
    r'https?://[a-z0-9.-]+',
    
    # Social media
    r'facebook\.com',
    r'twitter\.com',
    r'instagram\.com',
    
    # Generic headers/footers
    r'thank\s+you\s+for\s+choosing',
    r'visit\s+us\s+at',
    r'follow\s+us\s+on',
    
    # Document metadata
    r'printed\s+on',
    r'generated\s+on',
    r'page\s+total',
    
    # Contact headers
    r'contact\s+us',
    r'customer\s+care',
    r'helpline',
]


# =============================================================================
# Artifact Detection Functions
# =============================================================================


def is_artifact(item_name: str) -> bool:
    """
    Check if item is an OCR/admin artifact that should be ignored.
    
    Args:
        item_name: Item name to check
        
    Returns:
        True if item is an artifact, False otherwise
        
    Examples:
        >>> is_artifact("Page 1 of 2")
        True
        >>> is_artifact("Ph: +91-9876543210")
        True
        >>> is_artifact("info@hospital.com")
        True
        >>> is_artifact("Download our app")
        True
        >>> is_artifact("Bill No: 12345")
        True
        >>> is_artifact("MRI BRAIN")
        False
        >>> is_artifact("CONSULTATION")
        False
    """
    if not item_name:
        return True
    
    # Check against all patterns
    for pattern in IGNORE_PATTERNS:
        if re.search(pattern, item_name, re.IGNORECASE):
            return True
    
    # Check for very short items (likely artifacts)
    if len(item_name.strip()) < 3:
        return True
    
    # Check for items that are only special characters
    if re.match(r'^[^a-zA-Z0-9]+$', item_name):
        return True
    
    return False


def is_administrative_charge_v2(item_name: str) -> bool:
    """
    Enhanced check for administrative charges (Phase-2).
    
    Combines the original administrative charge detection with
    artifact detection for comprehensive filtering.
    
    Args:
        item_name: Item name to check
        
    Returns:
        True if item is an administrative charge or artifact
    """
    # Import original function
    from app.verifier.text_normalizer import is_administrative_charge
    
    # Check both administrative charges and artifacts
    return is_administrative_charge(item_name) or is_artifact(item_name)


def filter_artifacts(items: List[str]) -> List[str]:
    """
    Filter out artifacts from a list of item names.
    
    Args:
        items: List of item names
        
    Returns:
        List of non-artifact items
        
    Example:
        >>> items = ["MRI BRAIN", "Page 1 of 2", "CONSULTATION", "Ph: 123456"]
        >>> filter_artifacts(items)
        ['MRI BRAIN', 'CONSULTATION']
    """
    return [item for item in items if not is_artifact(item)]


# =============================================================================
# Testing
# =============================================================================

if __name__ == "__main__":
    # Test cases
    test_cases = [
        # Artifacts (should be True)
        ("Page 1 of 2", True),
        ("Ph: +91-9876543210", True),
        ("info@hospital.com", True),
        ("Download our app", True),
        ("Bill No: 12345", True),
        ("Date: 01/01/2024", True),
        ("www.hospital.com", True),
        ("Thank you for choosing us", True),
        
        # Valid items (should be False)
        ("MRI BRAIN", False),
        ("CONSULTATION", False),
        ("NICORANDIL 5MG", False),
        ("X-RAY CHEST", False),
        ("Blood Test - CBC", False),
    ]
    
    print("Artifact Detection Test Cases:")
    print("=" * 80)
    
    passed = 0
    failed = 0
    
    for item, expected in test_cases:
        result = is_artifact(item)
        status = "✅ PASS" if result == expected else "❌ FAIL"
        
        if result == expected:
            passed += 1
        else:
            failed += 1
        
        print(f"{status} | '{item}' → {result} (expected {expected})")
    
    print("=" * 80)
    print(f"Results: {passed} passed, {failed} failed")
