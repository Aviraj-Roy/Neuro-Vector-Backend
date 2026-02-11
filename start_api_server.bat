@echo off
echo ========================================
echo Medical Bill Verification API Server
echo ========================================
echo.
echo Starting backend server on http://localhost:8001
echo Interactive API docs: http://localhost:8001/docs
echo.
echo Press Ctrl+C to stop the server
echo ========================================
echo.

cd /d "%~dp0"
uvicorn backend.app.verifier.api:app --reload --port 8001 --host 0.0.0.0
