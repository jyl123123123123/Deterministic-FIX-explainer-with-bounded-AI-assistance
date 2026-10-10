# FIX Insight

FIX protocol message analyzer: a Python `fix_explainer` library (see B_INTEGRATION.md)
wrapped in a thin stdlib HTTP API, plus a React + TypeScript + Vite frontend.

## Run (two terminals, from the repo root)

```bash
# 1. API server on :8000 (no package install, no third-party deps; Python 3.11+)
PYTHONPATH=src python3 server/api_server.py

# 2. Frontend on :5173 (dev proxy forwards /api -> :8000)
cd frontend && npm install && npm run dev
```

Open http://localhost:5173. Without the API server the frontend falls back to
local in-browser parsing and shows a "Local mode (backend offline)" badge.

Gemini provider: set both `GEMINI_API_KEY` and `GEMINI_MODEL` before starting
the API server; otherwise the local template provider is used.
