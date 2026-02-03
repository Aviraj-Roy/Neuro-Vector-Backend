import os
from pathlib import Path
from dotenv import load_dotenv

# Base directory resolution (backend/app -> backend)
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
TIEUP_DIR = DATA_DIR / "tieups"
UPLOADS_DIR = BASE_DIR / "uploads"
PROCESSED_DIR = UPLOADS_DIR / "processed"

# Load environment variables from .env (check both backend/ and project root)
env_path = BASE_DIR / ".env"
if not env_path.exists():
    env_path = BASE_DIR.parent / ".env"
load_dotenv(dotenv_path=env_path if env_path.exists() else None)

# MongoDB configuration
MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
MONGO_DB_NAME = os.getenv("MONGO_DB_NAME", "medical_bills")

# OCR configuration
OCR_CONFIDENCE_THRESHOLD = float(
    os.getenv("OCR_CONFIDENCE_THRESHOLD", 0.6)
)