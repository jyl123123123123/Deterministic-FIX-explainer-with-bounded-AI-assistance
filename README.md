# FIX Insight

FIX protocol message analyzer: a Python `fix_explainer` library (see B_INTEGRATION.md)
wrapped in a thin stdlib HTTP API, plus a React + TypeScript + Vite frontend.

**Live demo (GitHub Pages):**
https://jyl123123123123.github.io/Deterministic-FIX-explainer-with-bounded-AI-assistance/

The hosted page has no Python backend, so message analysis runs in local
in-browser mode (yellow "Local mode (backend offline)" badge — expected). The
Gemini Chat panel works on the hosted page: click Edit in the chat header,
paste your own Gemini API key (get one at https://aistudio.google.com/api-keys),
optionally adjust the model, and Save. The key is stored only in your browser's
localStorage and sent only to Google's Gemini API.

## Run locally (two terminals, from the repo root)

```bash
# 1. API server on :8000 (no package install, no third-party deps; Python 3.11+)
PYTHONPATH=src python3 server/api_server.py

# 2. Frontend on :5173 (dev proxy forwards /api -> :8000)
cd frontend && npm install && npm run dev
```

Open http://localhost:5173. Without the API server the frontend falls back to
local in-browser parsing and shows a "Local mode (backend offline)" badge.

Gemini provider for the backend explainer: set both `GEMINI_API_KEY` and
`GEMINI_MODEL` before starting the API server; otherwise the local template
provider is used. (This is separate from the chat panel's browser-side key.)

## Deploy

`npm run build` in `frontend/` (build `base` is set to the Pages project path)
and publish `frontend/dist` to the `gh-pages` branch.
