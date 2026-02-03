"""
Main entry point for the Medical Bill Verification backend.
Run with: python backend/main.py
"""
from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

# Add backend directory to Python path to enable absolute imports
BACKEND_DIR = Path(__file__).resolve().parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

# Now we can import from app
from app.main import process_bill

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)


if __name__ == "__main__":
    """
    Example usage: Process a sample medical bill PDF.
    Replace 'Apollo.pdf' with your actual PDF path.
    """
    # Example PDF path - adjust as needed
    pdf_path = BACKEND_DIR.parent / "Apollo.pdf"
    
    if not pdf_path.exists():
        logger.error(f"PDF file not found: {pdf_path}")
        logger.info("Please provide a valid PDF path")
        sys.exit(1)
    
    logger.info(f"Processing bill: {pdf_path}")
    
    try:
        bill_id = process_bill(str(pdf_path))
        print(f"\n✅ Successfully processed bill!")
        print(f"Upload ID: {bill_id}")
    except Exception as e:
        logger.error(f"Failed to process bill: {e}", exc_info=True)
        sys.exit(1)
