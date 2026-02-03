"""
Test script for the Hospital Bill Verifier.

Usage:
    python -m tests.test_verifier

Note: Requires OPENAI_API_KEY environment variable to be set.
"""

import json
import os
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()


def test_verifier_with_sample_bill():
    """Test the verifier with a sample bill."""
    from app.verifier import (
        BillInput,
        BillVerifier,
        TieUpRateSheet,
        load_all_tieups,
    )
    
    # Check for API key
    if not os.getenv("OPENAI_API_KEY"):
        print("ERROR: OPENAI_API_KEY not set. Please set it in .env file.")
        return
    
    print("=" * 60)
    print("Hospital Bill Verifier Test")
    print("=" * 60)
    
    # Load tie-up rate sheets
    tieup_dir = os.getenv("TIEUP_DATA_DIR", "data/tieups")
    print(f"\n1. Loading tie-up rate sheets from: {tieup_dir}")
    
    rate_sheets = load_all_tieups(tieup_dir)
    print(f"   Loaded {len(rate_sheets)} rate sheets:")
    for rs in rate_sheets:
        print(f"   - {rs.hospital_name} ({len(rs.categories)} categories)")
    
    if not rate_sheets:
        print("ERROR: No rate sheets found. Add JSON files to data/tieups/")
        return
    
    # Initialize verifier
    print("\n2. Initializing verifier (building FAISS indices)...")
    verifier = BillVerifier(tieup_directory=tieup_dir)
    verifier.initialize(rate_sheets)
    print("   Verifier initialized successfully!")
    
    # Create sample bill
    print("\n3. Creating sample bill for verification...")
    sample_bill = BillInput(
        hospital_name="Apollo Hospitals Guwahati",  # Slightly different name to test semantic matching
        categories=[
            {
                "category_name": "Medicines",
                "items": [
                    # GREEN: Within allowed amount (10 × 2.50 = 25.00)
                    {"item_name": "Paracetamol 500mg Tab", "quantity": 10, "amount": 25.00},
                    # RED: Overcharged (5 × 8.00 = 40.00, but charged 55.00)
                    {"item_name": "Amoxicillin 500mg", "quantity": 5, "amount": 55.00},
                    # MISMATCH: Item not in tie-up
                    {"item_name": "Some Exotic Medicine XYZ", "quantity": 1, "amount": 500.00},
                ]
            },
            {
                "category_name": "Lab Tests",  # Slightly different category name
                "items": [
                    # Should match "Diagnostic Tests" category
                    {"item_name": "CBC Test", "quantity": 1, "amount": 350.00},
                    {"item_name": "Blood Sugar Fasting Test", "quantity": 1, "amount": 90.00},
                ]
            },
            {
                "category_name": "Room Charges",
                "items": [
                    # Should match "Hospitalization" category
                    {"item_name": "Private Room", "quantity": 3, "amount": 15000.00},
                ]
            }
        ]
    )
    
    print(f"   Hospital: {sample_bill.hospital_name}")
    print(f"   Categories: {len(sample_bill.categories)}")
    total_items = sum(len(cat.items) for cat in sample_bill.categories)
    print(f"   Total items: {total_items}")
    
    # Verify bill
    print("\n4. Running verification...")
    result = verifier.verify_bill(sample_bill)
    
    # Print results
    print("\n" + "=" * 60)
    print("VERIFICATION RESULTS")
    print("=" * 60)
    
    print(f"\nHospital: {result.hospital}")
    print(f"Matched to: {result.matched_hospital}")
    print(f"Hospital similarity: {result.hospital_similarity:.4f}")
    
    print("\n" + "-" * 60)
    for cat_result in result.results:
        print(f"\nCategory: {cat_result.category}")
        print(f"Matched to: {cat_result.matched_category}")
        print(f"Similarity: {cat_result.category_similarity:.4f}")
        print("\nItems:")
        
        for item in cat_result.items:
            status_symbol = {
                "GREEN": "✓",
                "RED": "✗",
                "MISMATCH": "?"
            }.get(item.status.value, "?")
            
            print(f"  [{status_symbol}] {item.bill_item}")
            print(f"      Status: {item.status.value}")
            print(f"      Bill Amount: ₹{item.bill_amount:.2f}")
            if item.matched_item:
                print(f"      Matched to: {item.matched_item}")
                print(f"      Allowed Amount: ₹{item.allowed_amount:.2f}")
                if item.extra_amount > 0:
                    print(f"      EXTRA CHARGED: ₹{item.extra_amount:.2f}")
            if item.similarity_score:
                print(f"      Similarity: {item.similarity_score:.4f}")
            print()
    
    # Summary
    print("=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"Total Bill Amount:    ₹{result.total_bill_amount:.2f}")
    print(f"Total Allowed Amount: ₹{result.total_allowed_amount:.2f}")
    print(f"Total Extra Amount:   ₹{result.total_extra_amount:.2f}")
    print()
    print(f"GREEN items:    {result.green_count}")
    print(f"RED items:      {result.red_count}")
    print(f"MISMATCH items: {result.mismatch_count}")
    
    # Return JSON output
    print("\n" + "=" * 60)
    print("JSON OUTPUT")
    print("=" * 60)
    print(result.model_dump_json(indent=2))
    
    return result


if __name__ == "__main__":
    test_verifier_with_sample_bill()
