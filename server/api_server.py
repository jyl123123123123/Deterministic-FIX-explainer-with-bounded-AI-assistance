#!/usr/bin/env python3
"""Compatibility launcher for the canonical FastAPI application (Python 3.11+)."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("fix_explainer.api:app", host="127.0.0.1", port=8000)
