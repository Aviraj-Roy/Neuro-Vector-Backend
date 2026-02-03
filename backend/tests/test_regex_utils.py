"""Unit tests for safe regex utilities.

Tests defensive regex handling for OCR text extraction edge cases:
- None matches
- Empty capture groups
- Multi-line fields
- Missing values
- OCR noise (missing colons, extra spaces, broken tokens)
"""

import sys
sys.path.insert(0, ".")

import re
from app.extraction.regex_utils import (
    safe_group,
    safe_match_value,
    clean_extracted_value,
    try_extract_labeled_field,
    is_label_only,
    extract_from_next_line,
    SafeFieldExtractor,
)


def test_safe_group_with_none():
    """Test safe_group handles None match gracefully."""
    print("Testing safe_group with None match...")
    
    # Pattern that doesn't match
    m = re.search(r"Patient Name:\s*(.+)", "Bill No: BL12345")
    result = safe_group(m, 1, "DEFAULT")
    
    assert result == "DEFAULT", f"Expected 'DEFAULT', got '{result}'"
    print("  ✓ None match returns default")


def test_safe_group_with_empty_group():
    """Test safe_group handles empty capture groups."""
    print("Testing safe_group with empty capture group...")
    
    # Pattern matches but group is empty (label with no value)
    m = re.search(r"Patient Name:\s*(.*)", "Patient Name:")
    result = safe_group(m, 1, "UNKNOWN")
    
    # Group exists but is empty string, should return empty string not default
    assert result == "", f"Expected '', got '{result}'"
    print("  ✓ Empty group returns empty string")


def test_safe_group_missing_group_index():
    """Test safe_group handles missing group indices."""
    print("Testing safe_group with missing group index...")
    
    # Pattern has no groups
    m = re.search(r"Patient Name:", "Patient Name:")
    result = safe_group(m, 1, "FALLBACK")
    
    assert result == "FALLBACK", f"Expected 'FALLBACK', got '{result}'"
    print("  ✓ Missing group index returns default")


def test_safe_match_value():
    """Test safe_match_value convenience function."""
    print("Testing safe_match_value...")
    
    # Successful extraction
    result = safe_match_value(r"Bill No:\s*(.+)", "Bill No: BL12345")
    assert result == "BL12345", f"Expected 'BL12345', got '{result}'"
    
    # No match
    result = safe_match_value(r"Bill No:\s*(.+)", "Patient Name: John")
    assert result == "", f"Expected '', got '{result}'"
    
    # Match but empty group
    result = safe_match_value(r"Bill No:\s*(.*)", "Bill No:")
    assert result == "", f"Expected '', got '{result}'"
    
    print("  ✓ safe_match_value working")


def test_clean_extracted_value():
    """Test value cleaning function."""
    print("Testing clean_extracted_value...")
    
    # Remove leading punctuation
    assert clean_extracted_value(": John Doe") == "John Doe"
    assert clean_extracted_value(". BL12345") == "BL12345"
    assert clean_extracted_value(".- Value") == "Value"
    
    # Normalize whitespace
    assert clean_extracted_value("John   Doe") == "John Doe"
    assert clean_extracted_value("  John Doe  ") == "John Doe"
    
    # Empty/None handling
    assert clean_extracted_value("") == ""
    assert clean_extracted_value(":::") == ""
    
    print("  ✓ Value cleaning working")


def test_try_extract_labeled_field():
    """Test labeled field extraction with validation."""
    print("Testing try_extract_labeled_field...")
    
    patterns = [r"patient\s*name\s*[:.]?", r"name\s*[:.]?"]
    
    # Normal extraction
    result = try_extract_labeled_field("Patient Name: John Doe", patterns)
    assert result == "John Doe", f"Expected 'John Doe', got '{result}'"
    
    # Label with colon and space
    result = try_extract_labeled_field("Patient Name : John Doe", patterns)
    assert result == "John Doe", f"Expected 'John Doe', got '{result}'"
    
    # Label without colon
    result = try_extract_labeled_field("Patient Name John Doe", patterns)
    assert result == "John Doe", f"Expected 'John Doe', got '{result}'"
    
    # Label only (no value) - should return None
    result = try_extract_labeled_field("Patient Name:", patterns)
    assert result is None, f"Expected None for label-only, got '{result}'"
    
    # Label with very short value (below min_value_len)
    result = try_extract_labeled_field("Patient Name: J", patterns, min_value_len=2)
    assert result is None, f"Expected None for short value, got '{result}'"
    
    print("  ✓ Labeled field extraction working")


def test_is_label_only():
    """Test label-only detection."""
    print("Testing is_label_only...")
    
    patterns = [r"patient\s*name\s*[:.]?"]
    
    # Label only cases
    assert is_label_only("Patient Name:", patterns) == True
    assert is_label_only("Patient Name :", patterns) == True
    assert is_label_only("Patient Name.", patterns) == True
    
    # Label with value
    assert is_label_only("Patient Name: John Doe", patterns) == False
    assert is_label_only("Patient Name John Doe", patterns) == False
    
    print("  ✓ Label-only detection working")


def test_extract_from_next_line():
    """Test multi-line extraction."""
    print("Testing extract_from_next_line...")
    
    patterns = [r"patient\s*name\s*[:.]?"]
    
    # Valid multi-line extraction
    result = extract_from_next_line("Patient Name:", "John Doe", patterns)
    assert result == "John Doe", f"Expected 'John Doe', got '{result}'"
    
    # Current line already has value (not label-only)
    result = extract_from_next_line("Patient Name: John", "Doe", patterns)
    assert result is None, f"Expected None, got '{result}'"
    
    # Next line is empty
    result = extract_from_next_line("Patient Name:", "", patterns)
    assert result is None, f"Expected None for empty next line, got '{result}'"
    
    # Next line is another label (has colon)
    result = extract_from_next_line("Patient Name:", "Bill No:", patterns)
    assert result is None, f"Expected None for next label, got '{result}'"
    
    # Next line is just a number
    result = extract_from_next_line("Patient Name:", "12345", patterns)
    assert result is None, f"Expected None for number, got '{result}'"
    
    print("  ✓ Multi-line extraction working")


def test_safe_field_extractor():
    """Test stateful field extractor with lookahead."""
    print("Testing SafeFieldExtractor...")
    
    lines = [
        "Hospital Name",
        "City Medical Centre",
        "Patient Name: John Doe",
        "Bill No:",
        "BL12345",
        "Date: 2024-01-15",
    ]
    
    label_patterns = {
        "patient_name": [r"patient\s*name\s*[:.]?"],
        "bill_number": [r"bill\s*no\s*[:.]?"],
        "date": [r"date\s*[:.]?"],
    }
    
    extractor = SafeFieldExtractor(lines, label_patterns)
    
    # Same-line extraction
    result = extractor.try_extract_at(2, "patient_name")
    assert result == "John Doe", f"Expected 'John Doe', got '{result}'"
    
    # Multi-line extraction
    result = extractor.try_extract_at(3, "bill_number")
    assert result == "BL12345", f"Expected 'BL12345', got '{result}'"
    
    # Same-line extraction with colon
    result = extractor.try_extract_at(5, "date")
    assert result == "2024-01-15", f"Expected '2024-01-15', got '{result}'"
    
    # Line already consumed (multi-line consumed both lines 3 and 4)
    result = extractor.try_extract_at(4, "bill_number")
    assert result is None, f"Expected None for consumed line, got '{result}'"
    
    print("  ✓ SafeFieldExtractor working")


def test_ocr_noise_patterns():
    """Test handling of common OCR noise patterns."""
    print("Testing OCR noise patterns...")
    
    patterns = [r"patient\s*name\s*[:.]?", r"bill\s*no\s*[:.]?"]
    
    # Missing colon
    result = try_extract_labeled_field("Patient Name John Doe", patterns)
    assert result == "John Doe", f"Missing colon failed: {result}"
    
    # Extra spaces
    result = try_extract_labeled_field("Patient   Name  :   John   Doe", patterns)
    assert result == "John Doe", f"Extra spaces failed: {result}"
    
    # Multiple punctuation
    result = try_extract_labeled_field("Patient Name:. John Doe", patterns)
    assert result == "John Doe", f"Multiple punctuation failed: {result}"
    
    # Case variations
    result = try_extract_labeled_field("PATIENT NAME: JOHN DOE", patterns)
    assert result == "JOHN DOE", f"Case variation failed: {result}"
    
    # Trailing punctuation on label
    result = try_extract_labeled_field("Bill No.:- BL12345", patterns)
    assert result == "BL12345", f"Trailing punctuation failed: {result}"
    
    print("  ✓ OCR noise handling working")


def test_edge_cases():
    """Test various edge cases."""
    print("Testing edge cases...")
    
    # Empty text
    result = try_extract_labeled_field("", [r"patient\s*name"])
    assert result is None, "Empty text should return None"
    
    # No patterns
    result = try_extract_labeled_field("Patient Name: John", [])
    assert result is None, "No patterns should return None"
    
    # Pattern doesn't match
    result = try_extract_labeled_field("Hospital: XYZ", [r"patient\s*name"])
    assert result is None, "Non-matching pattern should return None"
    
    # Value with special characters
    patterns = [r"patient\s*name\s*[:.]?"]
    result = try_extract_labeled_field("Patient Name: Mr. O'Brien (Sr.)", patterns)
    assert result == "Mr. O'Brien (Sr.)", f"Special chars failed: {result}"
    
    # Unicode characters (Indian names)
    result = try_extract_labeled_field("Patient Name: संजय कुमार", patterns)
    assert "संजय" in result, f"Unicode failed: {result}"
    
    print("  ✓ Edge cases handled")


def run_all_tests():
    """Run all test functions."""
    print("\n" + "=" * 60)
    print("Running Safe Regex Utilities Tests")
    print("=" * 60 + "\n")
    
    tests = [
        test_safe_group_with_none,
        test_safe_group_with_empty_group,
        test_safe_group_missing_group_index,
        test_safe_match_value,
        test_clean_extracted_value,
        test_try_extract_labeled_field,
        test_is_label_only,
        test_extract_from_next_line,
        test_safe_field_extractor,
        test_ocr_noise_patterns,
        test_edge_cases,
    ]
    
    passed = 0
    failed = 0
    
    for test in tests:
        try:
            test()
            passed += 1
        except AssertionError as e:
            print(f"  ✗ FAILED: {e}")
            failed += 1
        except Exception as e:
            print(f"  ✗ ERROR: {type(e).__name__}: {e}")
            failed += 1
    
    print("\n" + "=" * 60)
    print(f"Results: {passed} passed, {failed} failed")
    print("=" * 60)
    
    return failed == 0


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
