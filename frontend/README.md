# Frontend

This directory is reserved for future frontend development.

The backend is located in `../backend/` and can be run independently.

## Planned Integration

The frontend will communicate with the backend via:
- REST API endpoints (FastAPI server at `backend/app/verifier/api.py`)
- Default port: 8001

## Backend API Endpoints

Once implemented, the frontend can use these endpoints:

- `GET /health` - Health check
- `POST /verify` - Verify a bill JSON directly
- `POST /verify/{upload_id}` - Verify a bill from MongoDB
- `POST /tieups/reload` - Reload tie-up rate sheets
- `GET /tieups` - List loaded hospitals

## Running the Backend API

```bash
cd ../backend
uvicorn app.verifier.api:app --reload --port 8001
```

Then access at: `http://localhost:8001`
API docs at: `http://localhost:8001/docs`
