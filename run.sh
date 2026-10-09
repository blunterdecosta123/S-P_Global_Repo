#!/usr/bin/env bash
# Quickstart launcher for S&P Global & CRISIL AI/NLP Risk Engine
set -e

echo "=========================================================="
echo " Starting S&P Global & CRISIL AI/NLP Risk Engine Platform "
echo "=========================================================="

# Check Python environment
python3 -c "import sys; print(f'Python Runtime: {sys.version}')"

# Run FastAPI Server on http://localhost:8000
python3 -m uvicorn src.main:app --host 0.0.0.0 --port 8000 --reload
