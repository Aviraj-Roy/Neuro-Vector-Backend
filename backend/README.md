# Medical Bill Verification - Backend

This directory contains all backend code for the AI-Powered Medical Bill Verification system.

## Directory Structure

```
backend/
├── app/                    # Main application code
│   ├── classification/     # Bill classification logic
│   ├── db/                 # Database clients (MongoDB)
│   ├── extraction/         # Bill data extraction pipeline
│   ├── ingestion/          # PDF loading and conversion
│   ├── ocr/                # OCR engine (PaddleOCR)
│   ├── tools/              # CLI tools (embedding builder, etc.)
│   ├── utils/              # Utility functions
│   ├── verifier/           # Semantic matching & verification
│   ├── config.py           # Configuration and path resolution
│   └── main.py             # Core processing pipeline
├── data/                   # Data files
│   ├── tieups/             # Hospital tie-up rate sheets (JSON)
│   └── embedding_cache.json # Cached embeddings
├── tests/                  # Test files
├── uploads/                # Temporary image files (auto-cleaned)
│   └── processed/          # Preprocessed images
├── reports/                # Generated verification reports
├── main.py                 # Entry point - run with: python backend/main.py
└── requirements.txt        # Python dependencies

```

## Running the Backend

### Primary Entry Point

```bash
python backend/main.py
```

This is the main way to run the backend processing pipeline.

### Alternative: Run as Module

From the project root:
```bash
python -m backend.app.main
```

### Running Tests

```bash
# From backend directory
cd backend
python app/verifier/test_local_setup.py

# Or using pytest
pytest tests/
```

### Running the API Server

```bash
# From backend directory
cd backend
uvicorn app.verifier.api:app --reload --port 8001
```

## Path Resolution

All file paths in the backend use **pathlib-based resolution** relative to the backend directory:

- `BASE_DIR`: Points to `backend/`
- `DATA_DIR`: Points to `backend/data/`
- `TIEUP_DIR`: Points to `backend/data/tieups/`
- `UPLOADS_DIR`: Points to `backend/uploads/`
- `PROCESSED_DIR`: Points to `backend/uploads/processed/`

These are defined in `app/config.py` and ensure the backend works correctly regardless of where it's run from.

## Environment Variables

The backend looks for `.env` in two locations (in order):
1. `backend/.env`
2. Project root `.env`

Key environment variables:
- `MONGO_URI`: MongoDB connection string
- `MONGO_DB_NAME`: Database name
- `TIEUP_DATA_DIR`: Override default tie-up directory
- `EMBEDDING_CACHE_PATH`: Override default cache location
- `OCR_CONFIDENCE_THRESHOLD`: OCR confidence threshold

## Import Structure

All imports use absolute imports from the `app` package:

```python
from app.config import BASE_DIR, DATA_DIR
from app.verifier.matcher import SemanticMatcher
from app.extraction.bill_extractor import extract_bill_data
```

The `backend/main.py` entry point adds the backend directory to `sys.path` automatically.

## Frontend Integration

This backend is structured to work alongside a future `frontend/` directory at the project root:

```
project-root/
├── backend/        # This directory
├── frontend/       # Future frontend code
├── README.md       # Project documentation
└── .env            # Shared environment variables
```

The backend is completely self-contained and does not assume it's at the project root.
