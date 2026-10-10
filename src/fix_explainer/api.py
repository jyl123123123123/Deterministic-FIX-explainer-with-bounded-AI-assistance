"""Local HTTP API for browser clients; Gemini credentials stay server-side."""

from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException
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


class ExplainRequest(BaseModel):
    message: str = Field(min_length=1, max_length=128 * 1024)
    mode: Literal["template", "ai"] = "template"


class ExplainResponse(BaseModel):
    mode: str
    message: dict
    explanation: dict


FIXTURE_DIR = Path(__file__).resolve().parents[2] / "tests" / "fixtures"
SPECIFICATION = load_orchestra(FIXTURE_DIR / "fix_orchestra_subset.xml")

app = FastAPI(title="Deterministic FIX Explainer API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


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
        GeminiExplanationProvider()
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