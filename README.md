# FIX Insight

A deterministic FIX decoder and simulated trading-flow dashboard with optional,
bounded Gemini summaries. Order requests and confirmed fills are counted separately.
Statistics describe the connected FIX flow, not the whole market.

## Run locally

Python 3.11+ and Node.js are required. Use two terminals from the repository root:

```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install -e '.[test]'
.venv/bin/python examples/start_api.py
```

```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:5173. AI is disabled by default and no key is required.
`server/api_server.py` is now a compatibility launcher for the same FastAPI app;
there is one backend API contract. The interactive API documentation is at
http://127.0.0.1:8000/docs.

## Demo

1. Open **Trading Flow** and select a replay speed (10–100 messages/second).
2. Start a 1,500-message synthetic order lifecycle replay.
3. Watch demand quantities, confirmed fills, and per-currency monetary rankings.
4. Pause, resume, adjust speed, or stop. Starting another replay clears previous
   order state and statistics. The process-wide AI budget is retained.
5. Select **Template summary** for an offline, cited explanation. Expand the
   evidence snapshot to resolve JSON Pointer citations.

The Analyzer and Order Builder remain available. When no backend is reachable,
the Analyzer can use its separate browser implementation, explicitly labeled
Local mode; it does not provide server validation or trading analytics. API errors
and schema mismatches are shown rather than silently interpreted as connectivity
failures.

## Optional AI

```bash
export FIX_ENABLE_AI=1
export OPENAI_API_KEY=...            # OpenAI preferred
export OPENAI_MODEL=gpt-4o-mini      # optional; this is the default
.venv/bin/python examples/start_api.py
```

With `FIX_ENABLE_AI=1`, server-side AI features pick a provider from the
environment: **OpenAI first** (`OPENAI_API_KEY`, model `OPENAI_MODEL`,
default `gpt-4o-mini`), otherwise **Gemini** when `GEMINI_API_KEY` and
`GEMINI_MODEL` are both set. With neither, AI endpoints return an explicit
503 and no key is required.

This powers the **Gemini Analyst** panel's free-form chat (`POST /api/chat`)
and its natural-language trading-window summary
(`POST /api/analytics/free-summary`), plus the bounded Gemini summary path.
Credentials remain in backend process memory; browsers never hold a key.
AI may incur provider charges; leave it disabled for a no-call demonstration.

Gemini only selects/reorders approved facts with local citations. It never parses
FIX, calculates totals, or alters validation. Raw messages, account/order/session
IDs, and diagnostic free text are excluded from aggregate prompts. Aggregate
symbols and numeric metrics are disclosed. All AI HTTP requests share a maximum
of 20 attempts per process and a minimum interval of 10 seconds. Failures consume
attempts; no automatic retries. Successful identical aggregate snapshots are
cached. Failure/disabled/budget responses return a deterministic explanation.

Browser key entry has been removed. The **Gemini Analyst** panel's free-form
chat is served by the backend: with AI enabled it relays turns to Gemini via
`POST /api/chat` (same 20-calls-per-process budget and 10-second minimum
interval as summaries); with AI disabled it returns an explicit 503. Keys
formerly saved by an older frontend can be removed via the browser's site
storage controls; this version never reads or uses them. A frontend-only
GitHub Pages deployment cannot run the Python statistics or server-side
Gemini; use local full-stack demo or deploy the backend separately with
appropriate access controls.

## Verification

```bash
.venv/bin/python -m pytest
.venv/bin/python examples/analytics_demo.py
cd frontend
npm run build
```

Tests use mocked Gemini responses and never spend API quota. To check a real key
and quota, start the explicitly enabled backend and request one Gemini summary;
inspect `provider` and `fallback_reason`. Alternatively run
`.venv/bin/python examples/check_gemini.py` for one secure, opt-in live check. A template response is not proof of a
successful Gemini call. Do not put keys in source files, commits, or frontend env.

## Boundaries

The bridge supports FIX 4.4 synthetic lifecycle messages with whole-second UTC
SendingTime. Confirmed new fills require ExecType=F and OrdStatus=1/2. Unsupported
corrections and trade cancellations are excluded, not applied retroactively.
Statistics are in memory, with a 10,000-event bound. Multi-session production FIX,
fractional SendingTime support, correction processing, and durable analytics
recovery are outside the demo scope. Currency absent from input is UNSPECIFIED,
never implicitly USD. No FX conversion, contract multipliers, or aggressor-side
inference is performed. See B_INTEGRATION.md for API and evidence details.
