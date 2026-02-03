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
        # Step 1: Process and extract bill data
        bill_id = process_bill(str(pdf_path))
        print(f"\n✅ Successfully processed bill!")
        print(f"Upload ID: {bill_id}")
        
        # Step 2: Run verification (LLM comparison)
        logger.info("\n" + "="*80)
        logger.info("Running Bill Verification (LLM Comparison)")
        logger.info("="*80)
        
        try:
            from app.verifier.api import verify_bill_from_mongodb_sync
            from app.db.mongo_client import MongoDBClient
            
            # Fetch bill from MongoDB
            db = MongoDBClient(validate_schema=False)
            bill_doc = db.get_bill(bill_id)
            
            if not bill_doc:
                logger.warning("Bill not found in MongoDB for verification")
            else:
                # Run verification
                verification_result = verify_bill_from_mongodb_sync(bill_id)
                
                # Display verification results
                print("\n" + "="*80)
                print("VERIFICATION RESULTS")
                print("="*80)
                print(f"Hospital: {verification_result.get('hospital', 'N/A')}")
                print(f"Matched Hospital: {verification_result.get('matched_hospital', 'N/A')}")
                print(f"Hospital Similarity: {verification_result.get('hospital_similarity', 0):.2%}")
                print(f"\nSummary:")
                print(f"  ✅ GREEN (Match): {verification_result.get('green_count', 0)}")
                print(f"  ❌ RED (Overcharged): {verification_result.get('red_count', 0)}")
                print(f"  ⚠️  MISMATCH (Not Found): {verification_result.get('mismatch_count', 0)}")
                print(f"\nFinancial Summary:")
                print(f"  Total Bill Amount: ₹{verification_result.get('total_bill_amount', 0):.2f}")
                print(f"  Total Allowed Amount: ₹{verification_result.get('total_allowed_amount', 0):.2f}")
                print(f"  Total Extra Amount: ₹{verification_result.get('total_extra_amount', 0):.2f}")
                
                # Display category-wise results
                print(f"\nCategory-wise Results:")
                for cat_result in verification_result.get('results', []):
                    cat_name = cat_result.get('category', 'Unknown')
                    matched_cat = cat_result.get('matched_category', 'N/A')
                    print(f"\n  📁 {cat_name} → {matched_cat}")
                    
                    for item in cat_result.get('items', [])[:5]:  # Show first 5 items per category
                        status = item.get('status', 'UNKNOWN')
                        status_icon = "✅" if status == "GREEN" else "❌" if status == "RED" else "⚠️"
                        print(f"    {status_icon} {item.get('bill_item', 'N/A')[:50]} - {status}")
                        if status == "RED":
                            print(f"       Bill: ₹{item.get('bill_amount', 0):.2f}, Allowed: ₹{item.get('allowed_amount', 0):.2f}, Extra: ₹{item.get('extra_amount', 0):.2f}")
                
                print("\n" + "="*80)
                logger.info("Verification complete!")
                
        except ImportError as e:
            logger.warning(f"Verifier not available: {e}")
            logger.info("Skipping verification step")
        except Exception as e:
            logger.error(f"Verification failed: {e}", exc_info=True)
            logger.info("Bill was processed successfully, but verification encountered an error")
        
    except Exception as e:
        logger.error(f"Failed to process bill: {e}", exc_info=True)
        sys.exit(1)
