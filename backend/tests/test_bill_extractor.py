from app.extraction.bill_extractor import extract_bill_data

sample_text = """
Patient Name: John Doe
Hospital: City Medical Centre
Bill No: INV12345
Date: 12/09/2024

Paracetamol Tablet 500mg  ₹50.00
Blood Test CBC           ₹300.00
Consultation Fee         ₹500.00

GST: ₹45.00
Total: ₹895.00
"""

ocr_result = {"raw_text": sample_text}

bill_data = extract_bill_data(ocr_result)
print(bill_data)
