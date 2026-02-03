"""Smart Column Parser for Medical Bill Items.

Handles flexible column parsing with semantic context to avoid misclassification
of identifiers (MRN, Bill No, Age, Phone) as amounts/quantities.

Design principles:
- Detect table columns dynamically (no fixed order assumed)
- Use preceding tokens for semantic filtering
- Prevent identifier contamination
- Support qty × rate validation with discrepancy detection
"""

from __future__ import annotations

import re
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass

from app.extraction.numeric_guards import (
    is_suspect_numeric,
    extract_numeric_value,
    MAX_LINE_ITEM_AMOUNT,
)


# =============================================================================
# Semantic Context Keywords
# =============================================================================

# Tokens that indicate the following number is an identifier, NOT an amount
IDENTIFIER_KEYWORDS = [
    # Bill/invoice identifiers
    r"\bbill\s+(no|number|#)",
    r"\binvoice\s+(no|number|#)",
    r"\breceipt\s+(no|number|#)",
    r"\bvisit\s+(no|number)",
    
    # Patient identifiers
    r"\bmrn\b",
    r"\buhid\b",
    r"\bpatient\s+id\b",
    r"\breg\.?\s+(no|number)",
    
    # Personal data
    r"\bphone\b",
    r"\bmobile\b",
    r"\bcontact\b",
    r"\bage\b",
    r"\bdob\b",
    r"\bdate\s+of\s+birth\b",
    
    # Other identifiers
    r"\bpin\s*code\b",
    r"\bgstin?\b",
]

# Tokens that indicate the following number is a medical amount/rate
AMOUNT_KEYWORDS = [
    r"\bamount\b",
    r"\btotal\b",
    r"\brate\b",
    r"\bprice\b",
    r"\bcharge\b",
    r"\bfee\b",
    r"\bcost\b",
]

# Non-billable section indicators (skip these as items)
NON_BILLABLE_KEYWORDS = [
    r"\bpayment\b",
    r"\bpaid\b",
    r"\breceived\b",
    r"\badjusted\b",
    r"\bpatient\s+payable\b",
    r"\bsponsor\s+payable\b",
    r"\brounded\s+off\b",
    r"\bbalance\s+(due|to\s*pay)\b",
    r"\bnet\s+payable\b",
    r"\bgross\s+total\b",
    r"\bgrand\s+total\b",
]


def has_identifier_context(text: str, window_size: int = 50) -> bool:
    """Check if text contains identifier keywords in preceding context.
    
    Args:
        text: Text to check (description + columns combined)
        window_size: Characters to check before numeric value
        
    Returns:
        True if identifier context detected
    """
    if not text:
        return False
    
    check_text = text[-window_size:].lower()
    return any(re.search(pattern, check_text, re.IGNORECASE) for pattern in IDENTIFIER_KEYWORDS)


def is_non_billable_section(text: str) -> bool:
    """Check if text indicates a non-billable section.
    
    Args:
        text: Text to check
        
    Returns:
        True if non-billable section
    """
    if not text:
        return False
    
    t = text.lower()
    return any(re.search(pattern, t, re.IGNORECASE) for pattern in NON_BILLABLE_KEYWORDS)


# =============================================================================
# Column Parsing
# =============================================================================

@dataclass
class ParsedItem:
    """Parsed line item with qty, rate, amount fields."""
    description: str
    qty: Optional[float] = None
    unit_rate: Optional[float] = None
    pdf_amount: Optional[float] = None
    computed_amount: Optional[float] = None
    final_amount: Optional[float] = None
    discrepancy: bool = False
    raw_columns: List[str] = None
    
    def __post_init__(self):
        """Compute derived fields."""
        if self.raw_columns is None:
            self.raw_columns = []
        
        # Compute amount from qty × rate
        if self.qty is not None and self.unit_rate is not None:
            self.computed_amount = round(self.qty * self.unit_rate, 2)
        
        # Apply B2 rule: pdf_amount takes precedence if it differs
        if self.pdf_amount is not None and self.computed_amount is not None:
            diff = abs(self.pdf_amount - self.computed_amount)
            if diff > 0.02:  # 2 cent tolerance for rounding
                self.final_amount = self.pdf_amount
                self.discrepancy = True
            else:
                self.final_amount = self.computed_amount
                self.discrepancy = False
        elif self.pdf_amount is not None:
            self.final_amount = self.pdf_amount
            self.discrepancy = False
        elif self.computed_amount is not None:
            self.final_amount = self.computed_amount
            self.discrepancy = False
        else:
            # No amount at all - invalid item
            self.final_amount = None


def parse_numeric_column(text: str, preceding_context: str = "") -> Optional[float]:
    """Parse a numeric column with semantic filtering.
    
    Args:
        text: Column text
        preceding_context: Text before this column (for semantic filtering)
        
    Returns:
        Numeric value or None if invalid/identifier
    """
    if not text or not text.strip():
        return None
    
    # Quick reject: if preceding context has identifier keywords, skip
    if has_identifier_context(preceding_context):
        return None
    
    # Quick reject: if text itself is a suspect pattern (MRN, phone, etc.)
    if is_suspect_numeric(text.strip()):
        return None
    
    # Extract numeric value
    val = extract_numeric_value(text)
    if val is None:
        return None
    
    # Sanity check: reject absurd values
    if val > MAX_LINE_ITEM_AMOUNT or val < 0:
        return None
    
    return val


def parse_item_columns(
    description: str,
    columns: List[str],
    full_text: str = "",
) -> Optional[ParsedItem]:
    """Parse item columns into structured fields.
    
    Handles flexible column orders:
    - [desc, qty, rate, amount]
    - [desc, qty, amount]
    - [desc, amount]
    - Vertical/diagonal OCR artifacts
    
    Args:
        description: Item description
        columns: List of column values (may include description)
        full_text: Full line text for context
        
    Returns:
        ParsedItem or None if invalid
    """
    if not description or not description.strip():
        return None
    
    # Filter out description from columns if it appears
    numeric_cols = []
    accumulated_context = full_text[:100] if full_text else description[:100]
    
    for col in columns:
        if not col or not col.strip():
            continue
        
        # Skip if column is part of description
        if col.strip() in description:
            continue
        
        # Parse with semantic context
        val = parse_numeric_column(col, accumulated_context)
        if val is not None:
            numeric_cols.append(val)
        
        # Update context for next column
        accumulated_context += f" {col}"
    
    # Interpret numeric columns based on count
    qty: Optional[float] = None
    unit_rate: Optional[float] = None
    pdf_amount: Optional[float] = None
    
    if len(numeric_cols) == 0:
        # No numeric data - invalid item
        return None
    elif len(numeric_cols) == 1:
        # Only amount (qty defaults to 1)
        qty = 1.0
        pdf_amount = numeric_cols[0]
    elif len(numeric_cols) == 2:
        # Ambiguous: could be [qty, amount] or [rate, amount]
        # Heuristic: if first value is small (< 100), treat as qty
        if numeric_cols[0] < 100:
            qty = numeric_cols[0]
            pdf_amount = numeric_cols[1]
        else:
            # Treat as [rate, amount] with qty=1
            qty = 1.0
            unit_rate = numeric_cols[0]
            pdf_amount = numeric_cols[1]
    elif len(numeric_cols) >= 3:
        # Full triplet: [qty, rate, amount]
        qty = numeric_cols[-3]
        unit_rate = numeric_cols[-2]
        pdf_amount = numeric_cols[-1]
    
    return ParsedItem(
        description=description.strip(),
        qty=qty,
        unit_rate=unit_rate,
        pdf_amount=pdf_amount,
        raw_columns=columns,
    )


def is_valid_item(item: ParsedItem) -> bool:
    """Validate parsed item.
    
    Args:
        item: Parsed item
        
    Returns:
        True if valid billable item
    """
    if not item or not item.description:
        return False
    
    # Must have final_amount
    if item.final_amount is None or item.final_amount <= 0:
        return False
    
    # Description must not be a non-billable section
    if is_non_billable_section(item.description):
        return False
    
    # Description must have some alphabetic content
    if not re.search(r"[a-zA-Z]{2,}", item.description):
        return False
    
    return True
