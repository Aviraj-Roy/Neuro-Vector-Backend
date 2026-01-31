# Hospital Bill Verifier Module

A semantic matching and price verification system for hospital bills against tie-up rate sheets.

## Architecture

```
app/verifier/
├── __init__.py          # Package exports
├── models.py            # Pydantic schemas (Bill, TieUp, Results)
├── embedding_service.py # OpenAI-compatible embedding generation
├── matcher.py           # FAISS-based semantic matching
├── price_checker.py     # Price comparison logic
├── verifier.py          # Main orchestration service
├── api.py               # FastAPI endpoints
└── README.md            # This file
```

## Processing Flow

1. **Fetch bill JSON** from MongoDB
2. **Hospital semantic matching** using embeddings → Pick highest similarity hospital
3. **Category semantic matching** (threshold: 0.70)
   - If similarity < 0.70 → All items in category marked as "MISMATCH"
4. **Item semantic matching** (threshold: 0.85)
   - If similarity >= 0.85 → Match found
   - If similarity < 0.85 → "MISMATCH"
5. **Price comparison**
   - `allowed_amount = rate × quantity` (for unit type)
   - `bill_amount <= allowed` → "GREEN"
   - `bill_amount > allowed` → "RED" + extra_amount

## Quick Start

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Configure Environment

Copy `.env.example` to `.env` and fill in your values:

```bash
cp .env.example .env
```

Required variables:
- `OPENAI_API_KEY`: Your OpenAI API key
- `MONGO_URI`: MongoDB connection string

### 3. Add Tie-Up Rate Sheets

Place JSON files in `data/tieups/` directory. Example format:

```json
{
  "hospital_name": "Apollo Hospital",
  "categories": [
    {
      "category_name": "Medicines",
      "items": [
        {"item_name": "Paracetamol 500mg", "rate": 2.50, "type": "unit"},
        {"item_name": "X-Ray Chest", "rate": 350.00, "type": "service"}
      ]
    }
  ]
}
```

Item types:
- `unit`: Price per unit (rate × quantity)
- `service`: Fixed price (quantity ignored)
- `bundle`: Package price (quantity ignored)

### 4. Run the API

```bash
uvicorn app.verifier.api:app --reload --port 8001
```

API docs available at: http://localhost:8001/docs

## API Endpoints

### POST /verify
Verify a bill JSON directly.

```bash
curl -X POST http://localhost:8001/verify \
  -H "Content-Type: application/json" \
  -d '{
    "bill": {
      "hospital_name": "Apollo Hospitals",
      "categories": [
        {
          "category_name": "Medicines",
          "items": [
            {"item_name": "Paracetamol 500mg Tab", "quantity": 10, "amount": 30.00}
          ]
        }
      ]
    }
  }'
```

### POST /verify/{upload_id}
Verify a bill from MongoDB by upload_id.

```bash
curl -X POST http://localhost:8001/verify/abc123def456
```

### GET /health
Check API health and verifier status.

### POST /tieups/reload
Reload tie-up rate sheets from disk.

### GET /tieups
List all loaded tie-up hospitals.

## Output Format

```json
{
  "hospital": "Apollo Hospitals",
  "matched_hospital": "Apollo Hospital",
  "hospital_similarity": 0.95,
  "results": [
    {
      "category": "Medicines",
      "matched_category": "Medicines",
      "category_similarity": 0.98,
      "items": [
        {
          "bill_item": "Paracetamol 500mg Tab",
          "matched_item": "Paracetamol 500mg Tablet",
          "status": "GREEN",
          "bill_amount": 25.00,
          "allowed_amount": 25.00,
          "extra_amount": 0.0,
          "similarity_score": 0.92
        },
        {
          "bill_item": "Some Unknown Medicine",
          "matched_item": null,
          "status": "MISMATCH",
          "bill_amount": 100.00,
          "allowed_amount": 0.0,
          "extra_amount": 0.0,
          "similarity_score": 0.65
        }
      ]
    }
  ],
  "total_bill_amount": 125.00,
  "total_allowed_amount": 25.00,
  "total_extra_amount": 0.0,
  "green_count": 1,
  "red_count": 0,
  "mismatch_count": 1
}
```

## Status Codes

| Status | Meaning |
|--------|---------|
| GREEN | Bill amount ≤ allowed amount |
| RED | Bill amount > allowed amount (overcharged) |
| MISMATCH | No matching item found in tie-up rates |

## Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `CATEGORY_SIMILARITY_THRESHOLD` | 0.70 | Minimum similarity for category match |
| `ITEM_SIMILARITY_THRESHOLD` | 0.85 | Minimum similarity for item match |
| `EMBEDDING_MODEL` | text-embedding-3-small | OpenAI embedding model |
| `TIEUP_DATA_DIR` | data/tieups | Directory for tie-up JSON files |
