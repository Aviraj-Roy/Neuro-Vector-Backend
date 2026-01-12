import os
from dotenv import load_dotenv

# Load environment variables from .env
load_dotenv()

# MongoDB configuration
MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
MONGO_DB_NAME = os.getenv("MONGO_DB_NAME", "medical_bills")

# OCR configuration
OCR_CONFIDENCE_THRESHOLD = float(
    os.getenv("OCR_CONFIDENCE_THRESHOLD", 0.6)
)