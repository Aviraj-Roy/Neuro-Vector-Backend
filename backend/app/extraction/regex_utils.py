"""Safe regex utilities for OCR text extraction.

Provides defensive helpers for handling regex matches in noisy OCR text
where matches may be None or groups may not exist.
"""

from typing import Optional, Match, Pattern
import re


def safe_group(match: Optional[Match], group_idx: int = 1, default: str = "") -> str:
    """Safely extract a regex group with fallback.
    
    Args:
        match: Regex match object (may be None)
        group_idx: Group index to extract (default: 1)
        default: Default value if match is None or group doesn't exist
        
    Returns:
        Extracted group value or default
        
    Examples:
        >>> m = re.search(r"Patient Name:\s*(.+)", "Patient Name:")
        >>> safe_group(m, 1, "UNKNOWN")  # Returns "UNKNOWN" instead of crashing
        'UNKNOWN'
        
        >>> m = re.search(r"Bill No:\s*(.+)", "Bill No: BL12345")
        >>> safe_group(m, 1)
        'BL12345'
    """
    if match is None:
        return default
    
    try:
        group_value = match.group(group_idx)
        if group_value is None:
            return default
        return group_value
    except (IndexError, AttributeError):
        return default


def safe_match_value(pattern: str, text: str, group_idx: int = 1, 
                     flags: int = re.IGNORECASE, default: str = "") -> str:
    """Safely search for a pattern and extract a group in one call.
    
    Args:
        pattern: Regex pattern to search for
        text: Text to search in
        group_idx: Group index to extract
        flags: Regex flags
        default: Default value if no match or group missing
        
    Returns:
        Extracted group value or default
        
    Examples:
        >>> safe_match_value(r"Bill No:\s*(.+)", "Bill No: BL12345")
        'BL12345'
        
        >>> safe_match_value(r"Bill No:\s*(.+)", "Bill No:")
        ''
    """
    match = re.search(pattern, text, flags)
    return safe_group(match, group_idx, default)


def clean_extracted_value(value: str) -> str:
    """Clean up an extracted header value.
    
    Removes leading punctuation (colons, dots, dashes) and normalizes whitespace.
    
    Args:
        value: Raw extracted value
        
    Returns:
        Cleaned value
        
    Examples:
        >>> clean_extracted_value(": John Doe  ")
        'John Doe'
        
        >>> clean_extracted_value(".- BL12345")
        'BL12345'
    """
    if not value:
        return ""
    
    # Remove leading punctuation and whitespace
    value = re.sub(r"^[:.\-\s]+", "", value)
    # Normalize internal whitespace
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def try_extract_labeled_field(text: str, label_patterns: list[str], 
                               min_value_len: int = 1) -> Optional[str]:
    """Try to extract a field value using multiple label patterns.
    
    This handles the common case where a label like "Patient Name:" is followed
    by a value on the same line. Returns None if no valid extraction is possible.
    
    Args:
        text: Line of text to parse
        label_patterns: List of regex patterns that match the label
        min_value_len: Minimum length of extracted value to be considered valid
        
    Returns:
        Extracted value or None if extraction failed
        
    Examples:
        >>> patterns = [r"patient\\s*name\\s*[:.]?", r"name\\s*[:.]?"]
        >>> try_extract_labeled_field("Patient Name: John Doe", patterns)
        'John Doe'
        
        >>> try_extract_labeled_field("Patient Name:", patterns)  # No value
        None
    """
    if not text or not label_patterns:
        return None
    
    for pattern in label_patterns:
        # Try to match label + optional value
        # Use optional group to avoid crashes when value is missing
        full_pattern = pattern + r"\s*(.*)$"
        match = re.search(full_pattern, text, re.IGNORECASE)
        
        if match:
            raw_value = safe_group(match, 1, "")
            cleaned_value = clean_extracted_value(raw_value)
            
            # Only return if we got a meaningful value
            if len(cleaned_value) >= min_value_len:
                return cleaned_value
    
    return None


def is_label_only(text: str, label_patterns: list[str]) -> bool:
    """Check if text contains only a label without a value.
    
    This helps identify multi-line fields where the label is on one line
    and the value is on the next line.
    
    Args:
        text: Line of text to check
        label_patterns: List of regex patterns that match the label
        
    Returns:
        True if text contains label only, False otherwise
        
    Examples:
        >>> patterns = [r"patient\\s*name\\s*[:.]?"]
        >>> is_label_only("Patient Name:", patterns)
        True
        
        >>> is_label_only("Patient Name: John Doe", patterns)
        False
    """
    if not text or not label_patterns:
        return False
    
    for pattern in label_patterns:
        # Check if pattern matches but there's nothing substantial after it
        match = re.search(pattern + r"\s*(.*)$", text, re.IGNORECASE)
        if match:
            value_part = safe_group(match, 1, "")
            cleaned = clean_extracted_value(value_part)
            # If value is empty or very short (likely punctuation only), it's label-only
            if len(cleaned) < 2:
                return True
    
    return False


def extract_from_next_line(current_text: str, next_text: str, 
                           label_patterns: list[str]) -> Optional[str]:
    """Extract value from next line if current line has label only.
    
    Handles multi-line extraction patterns common in OCR:
    Line 1: Patient Name:
    Line 2: John Doe
    
    Args:
        current_text: Current line (should contain label)
        next_text: Next line (should contain value)
        label_patterns: Patterns that match the label
        
    Returns:
        Extracted value from next line, or None
        
    Examples:
        >>> patterns = [r"patient\\s*name\\s*[:.]?"]
        >>> extract_from_next_line("Patient Name:", "John Doe", patterns)
        'John Doe'
        
        >>> extract_from_next_line("Patient Name: Already here", "John Doe", patterns)
        None
    """
    if not is_label_only(current_text, label_patterns):
        return None
    
    if not next_text or len(next_text.strip()) < 2:
        return None
    
    # Basic validation: next line shouldn't be another label or amount
    next_cleaned = next_text.strip()
    
    # Skip if next line looks like another label
    if re.search(r"[:.]\s*$", next_cleaned):
        return None
    
    # Skip if next line is just a number (likely not a name/value)
    if re.match(r"^\d+\.?\d*$", next_cleaned):
        return None
    
    return next_cleaned


class SafeFieldExtractor:
    """Stateful extractor that handles multi-line fields with lookahead.
    
    Usage:
        extractor = SafeFieldExtractor(lines, label_patterns)
        for i, line in enumerate(lines):
            value = extractor.try_extract_at(i)
            if value:
                # Use extracted value
    """
    
    def __init__(self, lines: list[str], label_patterns: dict[str, list[str]]):
        """Initialize extractor.
        
        Args:
            lines: List of text lines to process
            label_patterns: Dict mapping field names to their label patterns
        """
        self.lines = lines
        self.label_patterns = label_patterns
        self._consumed_indices: set[int] = set()
    
    def try_extract_at(self, line_idx: int, field_name: str) -> Optional[str]:
        """Try to extract a field value at the given line index.
        
        Handles both same-line and multi-line extraction automatically.
        
        Args:
            line_idx: Index of the line to check
            field_name: Name of the field to extract
            
        Returns:
            Extracted value or None
        """
        if line_idx < 0 or line_idx >= len(self.lines):
            return None
        
        if line_idx in self._consumed_indices:
            return None
        
        patterns = self.label_patterns.get(field_name, [])
        if not patterns:
            return None
        
        current_line = self.lines[line_idx]
        
        # Try same-line extraction first
        value = try_extract_labeled_field(current_line, patterns)
        if value:
            self._consumed_indices.add(line_idx)
            return value
        
        # Try multi-line extraction (label on current, value on next)
        if is_label_only(current_line, patterns) and line_idx + 1 < len(self.lines):
            next_line = self.lines[line_idx + 1]
            value = extract_from_next_line(current_line, next_line, patterns)
            if value:
                self._consumed_indices.add(line_idx)
                self._consumed_indices.add(line_idx + 1)
                return value
        
        return None
