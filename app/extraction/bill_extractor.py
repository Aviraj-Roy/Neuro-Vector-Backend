import re
from typing import Dict, List


def extract_basic_fields(text: str) -> Dict:
    """
    Extract basic bill-level fields using regex.
    """
    patterns = {
        "patient_name": r"Patient\s*Name[:\-]?\s*(.*)",
        "hospital_name": r"(Hospital|Clinic|Medical Centre)[:\-]?\s*(.*)",
        "bill_number": r"(Bill|Invoice)\s*(No|Number)[:\-]?\s*(\w+)",
        "date": r"Date[:\-]?\s*([\d\/\-]+)",
        "total_amount": r"(Total|Grand Total)[:\-]?\s*₹?\s*([\d,]+\.\d{2})",
        "tax": r"(GST|Tax)[:\-]?\s*₹?\s*([\d,]+\.\d{2})"
    }

    extracted = {}

    for key, pattern in patterns.items():
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            extracted[key] = match.groups()[-1].strip()

    return extracted


def extract_line_items(text: str) -> Dict[str, List[Dict]]:
    """
    Extract line items and group them.
    """
    categories = {
        "medicines": [],
        "tests": [],
        "procedures": [],
        "services": []
    }

    lines = text.splitlines()

    for line in lines:
        amount_match = re.search(r"₹?\s*(\d+\.\d{2})$", line)
        if not amount_match:
            continue

        amount = float(amount_match.group(1))
        description = re.sub(r"₹?\s*\d+\.\d{2}$", "", line).strip()

        lower_desc = description.lower()

        item = {
            "description": description,
            "amount": amount
        }

        if any(word in lower_desc for word in ["tablet", "capsule", "syrup", "mg"]):
            categories["medicines"].append(item)
        elif any(word in lower_desc for word in ["x-ray", "scan", "mri", "blood"]):
            categories["tests"].append(item)
        elif any(word in lower_desc for word in ["surgery", "procedure", "operation"]):
            categories["procedures"].append(item)
        else:
            categories["services"].append(item)

    return categories


def extract_bill_data(ocr_result: Dict) -> Dict:
    """
    Main entry point for bill extraction.
    """
    raw_text = ocr_result["raw_text"]

    bill_data = extract_basic_fields(raw_text)
    bill_data["line_items"] = extract_line_items(raw_text)

    return bill_data
