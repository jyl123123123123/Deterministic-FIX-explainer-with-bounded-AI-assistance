# B Integration Guide: Bounded FIX Explanations

The explanation layer reuses the existing parser, specification loader, and validators. It provides a local template provider and optional Gemini assistance through the existing `BoundedExplanationProvider` protocol and `explain_with_provider` function.

## Requirements and setup

Python 3.11 or later is required. No third-party runtime dependencies are needed; pytest is needed for tests.

Run from the repository root:

```sh
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[test]'
python -m pytest
```

If your Python 3.11+ executable has a different name, substitute it in the first command. Both demos check the Python version before importing the package.

## Run the demos

```sh
# Local templates: no network or credentials.
python examples/gemini_demo.py

# Mock Gemini: exercises sanitization, request construction, and output validation.
python examples/gemini_demo.py --mock

# The original template example prints the complete deterministic result.
# Use only in a trusted local environment: that result is not redacted.
python examples/template_demo.py
```

Without installing the package, use `PYTHONPATH=src` with a Python 3.11+ interpreter.

### Real Gemini requests

Create an API key in [Google AI Studio](https://aistudio.google.com/api-keys). Choose a model ID available to your account that supports structured JSON output. There is no hardcoded default model.

In zsh, enter credentials without placing the key in command history:

```sh
read -s 'GEMINI_API_KEY?Gemini API key: '
export GEMINI_API_KEY
printf '\n'
read 'GEMINI_MODEL?Gemini model ID: '
export GEMINI_MODEL

python examples/gemini_demo.py --ai

# Optional: read a single message from a file.
python examples/gemini_demo.py --ai --file /absolute/path/message.fix

# Clear the key after use.
unset GEMINI_API_KEY
```

Environment variables apply to the current terminal and its child processes. `.env` files are ignored by Git but are not loaded automatically. Keep keys on the backend, never in frontend code or committed files.

The demo converts readable pipe delimiters to SOH before integrity checks. It loads only the repository's example specification subset; it does not establish support for all FIX messages or versions. Replace that subset with the appropriate trusted specification for your application.

## Interface integration

```python
from fix_explainer import (
    GeminiExplanationProvider,
    TemplateExplanationProvider,
    explain_with_provider,
)

# message: output from the existing split_message function.
# specification: output from the existing load_orchestra function.
# errors: additional integrity/schema findings.
provider = TemplateExplanationProvider()
# To enable Gemini instead:
# provider = GeminiExplanationProvider(timeout=20)

result = explain_with_provider(message, provider, specification, errors)
summary = result['provider_summary']
findings = result['deterministic']['validation_errors']
fallback_used = result['fallback_used']
fallback_reason = result['fallback_reason']
```

See `examples/gemini_demo.py` for a complete parsing and validation pipeline. Do not include `message.errors` in `errors`: the interface already adds parser findings. Providers do not run validation themselves. An empty findings list does not establish a successful business outcome.

Render `provider_summary` as plain text. Display deterministic findings separately in a controlled panel. Show fallback status explicitly; mock or fallback output must not be presented as a successful Gemini response.

## Disclosure policy

### Local templates

The default allowed tags are 35, 38, 40, 44, 54, 55, 59, 150, 39, 151, 14, and 6. Custom `allowed_tags` can only narrow this policy, including removal of tag 35 message-type and purpose claims.

Sensitive identifiers, including account, order, communication-party, participant, and login identifiers, have their values hidden. Other unlisted fields are omitted. Header sender/target fields are not included in the parser's body facts. Allowed business quantities, prices, and symbols can be displayed by the local template provider.

Field names, enum labels, and message purposes are used only when provided by the deterministic context. No FIX meanings are inferred from a hardcoded explanation dictionary.

### Gemini input

`build_ai_catalog(context)` creates a new disclosure-safe catalog rather than forwarding the original context. It retains source indexes and available tag/ordinal references without mutating the input.

The AI policy additionally hides Symbol values and nonnumeric field values. Allowed numeric business values have bounded lengths. Message types and specification labels are restricted to limited character patterns. Specification metadata must come from a trusted loader; character restrictions do not make user-supplied metadata trustworthy.

Raw messages, account/order values, arbitrary diagnostic text, and arbitrary uncertainty text are not sent. Numeric business values and source structure are still disclosed; this is data minimization, not universal anonymization.

**The `deterministic` and `fallback` objects retain original values and diagnostics. They are not redacted and must not be sent to the model or public logs.** The original deterministic summary inside `fallback` is also not guaranteed to be redacted. The fallback `provider_summary` hides business values and cites validation/uncertainty records.

## Bounded model output

Gemini can select wording variant 0 or 1 for each catalog entry and arrange the entries. The final English text and citations are rendered locally from approved variants.

The response must contain only:

```json
{
  "items": [
    {"source_id": "known_facts[0]", "variant": 0}
  ]
}
```

Every catalog source must appear exactly once. Local validation rejects additional prose or properties, invented sources, duplicate sources, omitted sources, invalid variants, invalid JSON, and duplicate JSON keys. Consequently, the model cannot hide validation findings or introduce a new trading conclusion by attaching a valid citation.

This mode provides AI-assisted presentation rather than unrestricted paraphrasing, trading analysis, or free-form question answering.

## Citation precision

Body facts include the parser's existing zero-based token `ordinal`. Message-type and purpose facts include `evidence_fields`.

`[tag=55; ordinal=7]` identifies the eighth token position in the original message. Malformed tokens also count toward token positions. Match the ordinal against `message.fields` to locate a parsed field. This distinguishes repeated tags but is not a repeating-group path or a group-structure validation.

Legacy contexts without ordinals explicitly display `occurrence unavailable`.

- `[known_facts[i]]` identifies a structured fact.
- `[validation_errors[i]]` identifies an original validation record.
- `[unknowns[i]]` identifies a recorded uncertainty.
- `[validation_errors]` can cite an empty findings list in a fallback display.

A missing required tag has no actual field occurrence. Its tag reference identifies the affected tag; the validation record is the evidence, not proof that the field exists.

## Failures and limits

Provider exceptions, empty responses, or non-string responses trigger the existing `explain_deterministically` fallback. The original fallback result and all validation findings are preserved. Providers receive a deep copy, so mutations cannot overwrite the deterministic result. Additional findings supplied as an iterable are materialized before use to preserve them during fallback.

Gemini failure categories:

| Exception type | Meaning |
| --- | --- |
| `AIConfigurationError` | Missing/invalid model or key configuration |
| `AIInputError` | Invalid source or input catalog limit exceeded |
| `AIOutputError` | Invalid, blocked, truncated, or oversized output |
| `AITransportError` | HTTP, network, or socket failure |

Fallback reasons display the exception type rather than potentially sensitive exception details.

Requests use a fixed Google HTTPS host, with the key in a header. There are no automatic retries, redirects, or request/response logs. The default socket-operation timeout is 20 seconds, configurable up to 60 seconds. It is **not a strict overall wall-clock deadline**. HTTP errors, including 401/403/429/5xx, trigger fallback without retry.

Catalogs are limited to 128 entries; catalog and response sizes are bounded at 128 KiB. Inputs outside these limits fall back rather than being silently truncated.

## Validation and scope

The regression suite covers disclosure filtering, input immutability, repeated-tag references, missing-field findings, output rejection, fallback preservation, configuration, socket timeout, oversized responses, and HTTP error handling. Run `python -m pytest` for the current results.

A real Gemini demo call has also completed successfully without fallback during integration. That confirms one working configuration, not future model availability, quota, or service behavior.

The supported scope is single-message bounded explanation. Free-form question answering, sequence correlation, repeating-group validation, a full FIX dictionary, and a web interface remain outside this layer's scope.

## Official API references

- [Gemini structured outputs](https://ai.google.dev/gemini-api/docs/structured-output)
- [Google GenerateContent API definition](https://github.com/googleapis/googleapis/blob/master/google/ai/generativelanguage/v1beta/generative_service.proto)


## Local browser API

The web UI calls `POST /api/explain` through Vite's proxy to `127.0.0.1:8000`.
Install the package and test dependencies in `.venv` using the setup above.
Start the frontend in one terminal:

```sh
cd frontend
npm ci
npm run dev -- --host 127.0.0.1 --port 5173
```

Start the API in another terminal from the repository root:

```sh
.venv/bin/python examples/start_api.py
```

The launcher uses existing GEMINI_API_KEY/GEMINI_MODEL environment variables or
prompts for them. The API key prompt is hidden. It does not save credentials to disk.
Keep this terminal running; Ctrl+C stops the API. Select **Gemini API** under
**Server explanation** in the browser, then click **Analyze Message**.
The local API returns original deterministic fields to the browser; use it only
in a trusted local session. A displayed fallback means Gemini did not succeed.

For template-only use without credentials:

```sh
.venv/bin/python -m uvicorn fix_explainer.api:app --host 127.0.0.1 --port 8000
```

Do not run both API commands simultaneously. The health endpoint is
`http://127.0.0.1:8000/api/health`. The current API loads the fixture specification
subset, so schema findings are limited to that subset.

## Trading analytics (B upgrade)

`analytics.py` consumes validated `AnalyticsEvent` records. `analytics_bridge.py`
connects A's parser and order correlator to the ledger, including the symbol and
side inherited from the matched order. A's parser is reused. Only FIX 4.4 new
orders and Execution Reports with ExecType=F and OrdStatus=1/2 contribute demand
or fills. Status reports and cancel requests never create fills. Invalid wire
messages, ambiguous duplicate tags, trade corrections/cancellations, and
correlation failures are excluded. Validation findings remain separate from AI.

The demo is one connected synthetic session per process. A's correlator has
process-wide order/ExecID namespaces: restart before starting an independent
replay with reused IDs. The standalone B ledger supports session-scoped IDs, but
this does not upgrade A's correlator to a production multi-session engine.
Corrections are excluded, not applied retroactively; snapshots are not an audited
corrected trading book. Currency is UNSPECIFIED when absent; never label it USD.
The bridge currently accepts whole-second SendingTime timestamps as produced by
A's generator; fractional timestamps require a future adapter extension.

### Offline verification

```bash
cd ~/Desktop/fix-explainer-team
.venv/bin/python examples/analytics_demo.py
.venv/bin/python -m pytest
```

Python 3.11+ is required. No Gemini call is made by the offline demo or tests.

### API for C

Start the **FastAPI** backend (the older `server/api_server.py` decoder server does
not provide these analytics endpoints):

```bash
.venv/bin/python -m uvicorn fix_explainer.api:app --host 127.0.0.1 --port 8000
```

Then start A's simulation and fetch B's snapshots:

```bash
curl -X POST 'http://127.0.0.1:8000/api/trading/start?count=1500&rate=25&seed=20261010'
curl 'http://127.0.0.1:8000/api/analytics/snapshot?window_seconds=300'
curl -X POST 'http://127.0.0.1:8000/api/analytics/summary?window_seconds=300'
```

Poll snapshots once per second. Fields include `snapshot_id`, UTC window bounds,
`symbols`, `currency_totals`, `total_executions`, `total_orders`, `previous_symbols`,
`anomalies`, `findings`, `sources`, and `limitations`. Decimal monetary fields are
**strings**; C should format them for display without summing different currencies.
Sort instrument rows within each currency for Top Bought / Top Sold. Each row
contains separate buy/sell order quantities, fill quantities, and notionals.
`observed_side_notional_difference` is observed session-side imbalance, **not**
market capital flow or aggressor-side direction. Quantities have instrument units;
no contract multiplier or FX conversion is supplied.

Window intervals are `(start, end]` in event time, anchored to the greatest
accepted event timestamp. Optional `as_of` on the snapshot endpoint accepts a
URL-encoded timezone-aware ISO timestamp. Late events update historical windows.
An anomaly requires fill quantity at least twice the previous equal window and
an absolute increase of at least 100 units, with a positive previous baseline.
This descriptive threshold is not a trading signal. Empty baselines produce no
surge claim. The ledger holds at most 10,000 accepted events and fails closed at
capacity; it is in memory, independently of A's SQLite raw storage.

The existing `/api/trading/snapshot` and WebSocket remain A's legacy output.
Use `/api/analytics/snapshot` for B's fill counts and monetary statistics.
C's current frontend is not automatically converted into a trading dashboard by
this backend change; C must connect the new endpoints and render the fields.

### Optional bounded Gemini aggregate summaries

AI aggregate summaries are disabled by default. To enable them, set
`FIX_ENABLE_AI=1` before starting FastAPI and supply `GEMINI_API_KEY` and
`GEMINI_MODEL` through the environment or the existing secure launcher:

```bash
export FIX_ENABLE_AI=1
.venv/bin/python examples/start_api.py
curl -X POST 'http://127.0.0.1:8000/api/analytics/summary?ai=true'
```

No automatic/background AI requests are scheduled. Only explicit `ai=true`
summary requests may call Gemini. Limit: 20 attempts per backend process, at least
10 seconds between attempts; failures consume attempts, no automatic retries.
Restarting resets the budget. Cache hits for identical snapshots reuse successful
summaries (up to 32 cached snapshots). These controls apply to **aggregate summary
calls**, not existing decoder AI calls or frontend ChatPanel calls. Enabled API
calls can incur provider charges; leave aggregate AI disabled for a no-call demo.

Gemini receives only approved aggregate wording and snapshot metric citations,
never order IDs, session IDs, account IDs, raw FIX messages, or credentials in
prompts. Instrument symbols are disclosed in aggregate mode. It selects/reorders
approved variants; it cannot invent conclusions. Coverage is bounded to the first
10 symbol/currency rows and 10 anomalies. References contain the snapshot hash
and JSON Pointer within the returned `report`, rather than pretending aggregate
metrics refer to a single raw tag occurrence. Retain the returned report alongside
the summary for reproducible citations.

Responses contain `report`, `summary`, `provider`, `fallback_used`,
`fallback_reason`, `cached`, and `snapshot_id`. Disabled AI, throttling, exhausted
budgets, transport failures, and invalid selections return a cited deterministic
summary with a sanitized reason. Counts and validation findings are unchanged.
The Gemini network path is covered by mocked transport tests; live account access
and quota must be checked separately with an explicitly enabled call.
