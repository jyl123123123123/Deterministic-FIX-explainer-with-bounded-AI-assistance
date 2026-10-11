"""Local HTTP API for browser clients; AI credentials stay server-side."""

from pathlib import Path
import asyncio
import http.client
import json
import os
import re
from datetime import datetime
from threading import Lock
from time import monotonic
from .analytics import TradingAnalytics
from .analytics_bridge import AnalyticsBridge
from .analytics_summary import TradingSummaryService
from typing import Literal

from fastapi import FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from .ai import (
    AIOutputError,
    AITransportError,
    GeminiExplanationProvider,
    gemini_transport,
)
from .explainer import explain_with_provider
from .integrity import validate_integrity
from .schema import validate_message_schema
from .serialization import message_to_dict
from .spec import load_orchestra
from .template import TemplateExplanationProvider
from .message import split_message
from .streaming import StreamConfig, StreamSimulator
from .trading import TradingDataService


class ExplainRequest(BaseModel):
    message: str = Field(min_length=1, max_length=128 * 1024)
    mode: Literal["template", "ai"] = "template"


class ChatMessage(BaseModel):
    role: Literal["user", "model"]
    text: str = Field(min_length=1, max_length=4000)


class ChatRequest(BaseModel):
    messages: list[ChatMessage] = Field(min_length=1, max_length=40)


class ChatResponse(BaseModel):
    reply: str
    provider: str


class ExplainResponse(BaseModel):
    mode: str
    message: dict
    explanation: dict
    provider: str
    provider_summary: str
    deterministic: dict
    fallback_used: bool
    fallback_reason: str | None


FIXTURE_DIR = Path(__file__).resolve().parent / "data"
SPECIFICATION = load_orchestra(FIXTURE_DIR / "fix_orchestra_subset.xml")

app = FastAPI(title="Deterministic FIX Explainer API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)
analytics = TradingAnalytics()
trading_service = TradingDataService(event_observer=AnalyticsBridge(analytics))
summary_service = TradingSummaryService(enabled=os.environ.get("FIX_ENABLE_AI") == "1")
def ingest_current(message):
    return trading_service.ingest(message)


stream_simulator = StreamSimulator(ingest_current)
active_run_id = None


class BudgetedMessageProvider:
    def summarize(self, context):
        from .ai import AIConfigurationError
        with summary_service.lock:
            if not summary_service.enabled:
                raise AIConfigurationError("AI disabled")
            now = summary_service.clock()
            if summary_service.calls >= summary_service.max_calls or (
                summary_service.last_call is not None and now - summary_service.last_call < summary_service.interval
            ):
                raise AIConfigurationError("AI budget or interval limit")
            summary_service.calls += 1
            summary_service.last_call = now
            return GeminiExplanationProvider().summarize(context)



@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


CHAT_SYSTEM_INSTRUCTION = (
    "You are a helpful assistant embedded in FIX Insight, a FIX protocol "
    "message analyzer. Answer concisely. You may answer in the user's language."
)
CHAT_MAX_TOTAL_CHARS = 64 * 1024
CHAT_TIMEOUT_SECONDS = 20


class ChatRateLimiter:
    """Same parameters as the summary AI budget: 20 calls per process, 10s apart."""

    def __init__(self, max_calls: int = 20, interval: float = 10, clock=monotonic):
        self.max_calls, self.interval = max_calls, interval
        self.clock, self.calls, self.last_call = clock, 0, None
        self.lock = Lock()

    def check(self) -> str | None:
        """Consume one call slot, or return a reason token if not allowed."""
        with self.lock:
            if self.calls >= self.max_calls:
                return "AI_BUDGET_EXHAUSTED"
            if self.last_call is not None and self.clock() - self.last_call < self.interval:
                return "AI_RATE_LIMITED"
            self.calls += 1
            self.last_call = self.clock()
            return None


chat_limiter = ChatRateLimiter()

OPENAI_MAX_BYTES = 128 * 1024
DEFAULT_OPENAI_MODEL = "gpt-4o-mini"


def openai_transport(model, api_key, payload, timeout):
    """Fixed HTTPS host, key in Authorization header, no retries/logging.

    Mirrors ai.gemini_transport: socket-level timeout, bounded response size,
    and credential-free exceptions.
    """
    connection = http.client.HTTPSConnection("api.openai.com", timeout=timeout)
    try:
        connection.request(
            "POST",
            "/v1/chat/completions",
            body=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"},
        )
        response = connection.getresponse()
        if response.status != 200:
            raise AITransportError(f"OpenAI HTTP {response.status}")
        raw = response.read(OPENAI_MAX_BYTES + 1)
        if len(raw) > OPENAI_MAX_BYTES:
            raise AIOutputError("OpenAI response too large")
        data = json.loads(raw)
        choices = data.get("choices", [])
        if len(choices) != 1:
            raise AIOutputError("OpenAI response incomplete")
        text = choices[0].get("message", {}).get("content", "")
        if not isinstance(text, str) or not text.strip():
            raise AIOutputError("OpenAI returned no answer")
        return text
    except (AIOutputError, AITransportError):
        raise
    except Exception:
        # Never expose payload, key, or remote error body in exceptions.
        raise AITransportError("OpenAI request failed") from None
    finally:
        connection.close()


def _to_openai_messages(payload: dict) -> list[dict]:
    """Convert a Gemini-style payload (systemInstruction + contents) to
    OpenAI chat.completions messages (system + user/assistant)."""
    messages: list[dict] = []
    system_text = " ".join(
        part.get("text", "") for part in payload.get("systemInstruction", {}).get("parts", [])
    ).strip()
    if system_text:
        messages.append({"role": "system", "content": system_text})
    for content in payload.get("contents", []):
        role = "assistant" if content.get("role") == "model" else "user"
        text = "".join(part.get("text", "") for part in content.get("parts", []))
        messages.append({"role": role, "content": text})
    return messages


def _ai_config() -> tuple[str, str, str]:
    """Return (provider, model, key); OpenAI preferred, Gemini as fallback."""
    if os.environ.get("FIX_ENABLE_AI") != "1":
        raise HTTPException(
            status_code=503,
            detail="AI is not enabled on this server (set FIX_ENABLE_AI=1 with OPENAI_API_KEY, or GEMINI_API_KEY and GEMINI_MODEL).",
        )
    openai_key = os.environ.get("OPENAI_API_KEY", "")
    if openai_key.strip() and "\n" not in openai_key and "\r" not in openai_key:
        model = os.environ.get("OPENAI_MODEL", "").strip() or DEFAULT_OPENAI_MODEL
        return "openai", model, openai_key
    model = os.environ.get("GEMINI_MODEL", "")
    key = os.environ.get("GEMINI_API_KEY", "")
    if (
        isinstance(model, str)
        and re.fullmatch(r"gemini-[A-Za-z0-9._-]{1,100}", model)
        and key.strip()
        and "\n" not in key
        and "\r" not in key
    ):
        return "gemini", model, key
    raise HTTPException(status_code=503, detail="AI is not configured on this server.")


def _ai_generate(payload: dict) -> tuple[str, str]:
    """Rate-limited AI call; returns (reply, provider). Payload is
    Gemini-style; converted to OpenAI format when OpenAI is configured."""
    provider, model, key = _ai_config()
    limited = chat_limiter.check()
    if limited == "AI_BUDGET_EXHAUSTED":
        raise HTTPException(status_code=429, detail="AI call budget exhausted for this server process.")
    if limited is not None:
        raise HTTPException(status_code=429, detail="AI rate limit: please retry in a few seconds.")
    try:
        if provider == "openai":
            body = {
                "model": model,
                "messages": _to_openai_messages(payload),
                "temperature": 0.7,
                "max_tokens": 1000,
            }
            reply = openai_transport(model, key, body, CHAT_TIMEOUT_SECONDS)
        else:
            reply = gemini_transport(model, key, payload, CHAT_TIMEOUT_SECONDS)
    except AITransportError as error:
        match = re.search(r"HTTP (\d+)", str(error))
        upstream = int(match.group(1)) if match else None
        if upstream in (401, 403):
            detail = "The server AI API key was rejected."
        elif upstream == 404:
            detail = "The configured AI model is unavailable."
        elif upstream == 429:
            raise HTTPException(status_code=429, detail="AI provider rate limit reached; retry later.") from error
        else:
            detail = "AI request failed."
        raise HTTPException(status_code=502, detail=detail) from error
    except AIOutputError as error:
        raise HTTPException(status_code=502, detail="AI returned an unusable reply.") from error
    if not reply.strip():
        raise HTTPException(status_code=502, detail="AI returned an empty reply.")
    return reply, provider


@app.post("/api/chat", response_model=ChatResponse)
def chat(request: ChatRequest) -> ChatResponse:
    """Server-side AI chat; the browser never sees credentials."""
    _ai_config()
    if sum(len(m.text) for m in request.messages) > CHAT_MAX_TOTAL_CHARS:
        raise HTTPException(status_code=400, detail="Conversation is too long (64 KiB total).")

    # Normalize for multi-turn APIs: drop leading model messages and merge
    # consecutive same-role messages.
    contents: list[dict] = []
    for message in request.messages:
        if not contents and message.role == "model":
            continue
        if contents and contents[-1]["role"] == message.role:
            contents[-1]["parts"][0]["text"] += "\n" + message.text
        else:
            contents.append({"role": message.role, "parts": [{"text": message.text}]})
    if not contents:
        raise HTTPException(status_code=400, detail="At least one user message is required.")

    payload = {
        "systemInstruction": {"parts": [{"text": CHAT_SYSTEM_INSTRUCTION}]},
        "contents": contents,
    }
    reply, provider = _ai_generate(payload)
    return ChatResponse(reply=reply, provider=provider)


FREE_SUMMARY_INSTRUCTION = (
    "You are an analyst for a FIX trading-flow dashboard. Given these "
    "statistics (simulated data), write a natural, concise summary in "
    "English: which companies dominate, buy/sell volumes and "
    "notional, the rough sector/industry of each symbol based on your "
    "knowledge (e.g. AAPL = tech/consumer electronics), and any notable "
    "imbalances or anomalies. 3-6 short paragraphs or bullet points. "
    "Plain text, no citations, no markdown tables. State that the data "
    "is simulated."
)

_SYMBOL_STAT_KEYS = (
    "symbol",
    "currency",
    "buy_order_qty",
    "sell_order_qty",
    "buy_fill_qty",
    "sell_fill_qty",
    "buy_notional",
    "sell_notional",
)


def _compact_report(report: dict) -> dict:
    """Keep only the key numeric fields so the prompt stays small."""
    return {
        "simulated": True,
        "window_seconds": report.get("window_seconds"),
        "window_end": report.get("window_end"),
        "total_orders": report.get("total_orders"),
        "total_executions": report.get("total_executions"),
        "symbols": [
            {key: row.get(key) for key in _SYMBOL_STAT_KEYS}
            for row in report.get("symbols", [])
        ],
        "anomalies": [
            {
                "symbol": a.get("symbol"),
                "side": a.get("side"),
                "previous": a.get("previous"),
                "current": a.get("current"),
            }
            for a in report.get("anomalies", [])
        ],
        "findings": report.get("findings", {}),
    }


@app.post("/api/analytics/free-summary", response_model=ChatResponse)
def analytics_free_summary(window_seconds: int = Query(default=300, ge=1, le=86400)) -> ChatResponse:
    """Natural-language English summary of the current window via Gemini."""
    report = analytics.snapshot(window_seconds)
    if not report.get("total_executions") and not report.get("symbols"):
        return ChatResponse(
            reply="No data in the current statistics window. Start a replay on the Trading Flow page first.",
            provider="none",
        )
    stats = json.dumps(_compact_report(report), ensure_ascii=False)
    payload = {
        "systemInstruction": {"parts": [{"text": FREE_SUMMARY_INSTRUCTION}]},
        "contents": [{"role": "user", "parts": [{"text": f"Trading-flow statistics JSON:\n{stats}"}]}],
    }
    reply, provider = _ai_generate(payload)
    return ChatResponse(reply=reply, provider=provider)


@app.get("/api/analytics/snapshot")
def analytics_snapshot(window_seconds: int = Query(default=300, ge=1, le=86400), as_of: datetime | None = None) -> dict:
    try:
        return analytics.snapshot(window_seconds, as_of)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@app.post("/api/analytics/summary")
def analytics_summary(window_seconds: int = Query(default=300, ge=1, le=86400), ai: bool = False) -> dict:
    report = analytics.snapshot(window_seconds)
    return {"report": report, **summary_service.summarize(report, use_ai=ai)}


@app.get("/api/trading/snapshot")
def trading_snapshot() -> dict:
    return trading_service.snapshot()


@app.get("/api/trading/active")
def active_trading_run() -> dict | None:
    return stream_simulator.status(active_run_id) if active_run_id else None


@app.post("/api/trading/start")
async def start_trading_stream(
    count: int = Query(default=1500, ge=1000, le=2000),
    rate: int = Query(default=25, ge=10, le=100),
    seed: int = Query(default=20261010),
) -> dict:
    global analytics, trading_service, active_run_id
    if active_run_id and stream_simulator.status(active_run_id)["status"] in ("RUNNING", "PAUSED"):
        raise HTTPException(status_code=409, detail="A replay is already active.")
    config = StreamConfig(count=count, rate=rate, seed=seed)
    trading_service.close()
    analytics = TradingAnalytics()
    trading_service = TradingDataService(event_observer=AnalyticsBridge(analytics))
    try:
        run = stream_simulator.start(config)
        active_run_id = run.run_id
    except (RuntimeError, ValueError) as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    return run.snapshot()


@app.post("/api/trading/runs/{run_id}/{action}")
async def control_run(run_id: str, action: Literal["pause", "resume", "stop"], rate: int | None = Query(default=None, ge=10, le=100)) -> dict:
    try:
        if action == "stop":
            return (await stream_simulator.stop(run_id)).snapshot()
        return stream_simulator.control(run_id, action, rate).snapshot()
    except KeyError as error:
        raise HTTPException(status_code=404, detail="Unknown run") from error
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@app.get("/api/trading/runs/{run_id}")
def trading_run_status(run_id: str) -> dict:
    try:
        return stream_simulator.status(run_id)
    except KeyError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@app.websocket("/api/trading/stream")
async def trading_stream(websocket: WebSocket) -> None:
    await websocket.accept()
    last_processed = -1
    try:
        while True:
            snapshot = trading_service.snapshot()
            if snapshot["processed"] != last_processed:
                await websocket.send_json(snapshot)
                last_processed = snapshot["processed"]
            await asyncio.sleep(0.1)
    except WebSocketDisconnect:
        return


@app.post("/api/explain", response_model=ExplainResponse)
def explain(request: ExplainRequest) -> ExplainResponse:
    try:
        payload, delimiter = normalize_message(request.message)
    except UnicodeEncodeError as error:
        raise HTTPException(status_code=400, detail="FIX message must contain ASCII text.") from error

    parsed = split_message(payload, delimiter=delimiter)
    errors = (
        *validate_integrity(payload, parsed, delimiter),
        *validate_message_schema(parsed, SPECIFICATION),
    )
    provider = (
        BudgetedMessageProvider()
        if request.mode == "ai"
        else TemplateExplanationProvider()
    )
    explanation = explain_with_provider(
        parsed,
        provider,
        SPECIFICATION,
        errors,
    )
    return ExplainResponse(
        mode=request.mode,
        message=message_to_dict(parsed, errors),
        explanation=explanation,
        provider="gemini" if request.mode == "ai" and not explanation["fallback_used"] else "template",
        provider_summary=explanation["provider_summary"],
        deterministic=explanation["deterministic"],
        fallback_used=explanation["fallback_used"],
        fallback_reason=explanation["fallback_reason"],
    )


def normalize_message(value: str) -> tuple[bytes, bytes]:
    """Accept readable pipe/caret input or a literal FIX SOH delimiter."""
    payload = value.rstrip("\r\n").encode("ascii")
    if b"\x01" in payload:
        return payload, b"\x01"
    if b"^" in payload and b"|" not in payload:
        return payload.replace(b"^", b"\x01"), b"\x01"
    return payload.replace(b"|", b"\x01"), b"\x01"


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("fix_explainer.api:app", host="127.0.0.1", port=8000, reload=False)