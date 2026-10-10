"""Local HTTP API for browser clients; Gemini credentials stay server-side."""

from pathlib import Path
import asyncio
import os
from datetime import datetime
from .analytics import TradingAnalytics
from .analytics_bridge import AnalyticsBridge
from .analytics_summary import TradingSummaryService
from typing import Literal

from fastapi import FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from .ai import GeminiExplanationProvider
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