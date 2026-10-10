#!/usr/bin/env python3
"""Minimal stdlib HTTP wrapper around the fix_explainer pipeline.

Run from the repository root (no package install needed):

    PYTHONPATH=src python3 server/api_server.py

Endpoints:
    GET  /api/health   -> {"ok": true, "provider": "template" | "gemini"}
    POST /api/explain  -> bounded explanation for one FIX message

The provider is TemplateExplanationProvider by default (no network, no
credentials). If both GEMINI_API_KEY and GEMINI_MODEL are set in the
environment, GeminiExplanationProvider(timeout=20) is used instead.
API keys are never printed, logged, or included in responses.
"""
import json
import os
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))  # also works without PYTHONPATH=src

from fix_explainer import (  # noqa: E402
    TemplateExplanationProvider,
    explain_with_provider,
    load_orchestra,
    message_to_dict,
    split_message,
    validate_integrity,
    validate_message_schema,
)

SPEC = load_orchestra(ROOT / "tests" / "fixtures" / "fix_orchestra_subset.xml")

MAX_BODY_BYTES = 64 * 1024
ALLOWED_ORIGIN = "http://localhost:5173"
PORT = 8000


def build_provider():
    """Pick the explanation provider from the environment.

    Returns (provider, name). Never logs or returns the API key itself.
    """
    if os.environ.get("GEMINI_API_KEY") and os.environ.get("GEMINI_MODEL"):
        from fix_explainer import GeminiExplanationProvider

        return GeminiExplanationProvider(timeout=20), "gemini"
    return TemplateExplanationProvider(), "template"


PROVIDER, PROVIDER_NAME = build_provider()


def to_soh_payload(text: str) -> bytes:
    """Accept |, ^, or already-SOH delimited input; normalize to SOH bytes."""
    if "\x01" in text:
        return text.encode("utf-8", errors="replace")
    if "|" in text:
        return text.replace("|", "\x01").encode("utf-8", errors="replace")
    if "^" in text:
        return text.replace("^", "\x01").encode("utf-8", errors="replace")
    return text.encode("utf-8", errors="replace")


def explain_message(raw: str) -> dict:
    payload = to_soh_payload(raw.strip())
    message = split_message(payload)
    if not message.fields:
        raise ValueError("No FIX tag=value fields could be parsed from the message.")
    errors = (
        *validate_integrity(payload, message),
        *validate_message_schema(message, SPEC),
    )
    result = explain_with_provider(message, PROVIDER, SPEC, errors)
    return {
        "provider": PROVIDER_NAME,
        **result,
        "message": message_to_dict(message),
    }


class ApiHandler(BaseHTTPRequestHandler):
    server_version = "FixInsightAPI/0.1"

    def _cors_headers(self) -> None:
        self.send_header("Access-Control-Allow-Origin", ALLOWED_ORIGIN)
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def _send_json(self, status: int, obj: dict) -> None:
        body = json.dumps(obj, default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self._cors_headers()
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self._cors_headers()
        self.end_headers()

    def do_GET(self) -> None:
        if self.path == "/api/health":
            self._send_json(200, {"ok": True, "provider": PROVIDER_NAME})
        else:
            self._send_json(404, {"error": "Not found."})

    def do_POST(self) -> None:
        if self.path != "/api/explain":
            self._send_json(404, {"error": "Not found."})
            return
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            self._send_json(400, {"error": "Invalid Content-Length."})
            return
        if length <= 0 or length > MAX_BODY_BYTES:
            self._send_json(400, {"error": "Missing or oversized request body."})
            return
        try:
            request = json.loads(self.rfile.read(length))
        except (json.JSONDecodeError, UnicodeDecodeError):
            self._send_json(400, {"error": "Request body must be valid JSON."})
            return
        raw = request.get("message") if isinstance(request, dict) else None
        if not isinstance(raw, str) or not raw.strip():
            self._send_json(400, {"error": 'Field "message" must be a non-empty string.'})
            return
        try:
            self._send_json(200, explain_message(raw))
        except ValueError as exc:
            self._send_json(400, {"error": str(exc)})
        except Exception:
            # Never leak internal exception details (or secrets) to clients.
            self._send_json(500, {"error": "Internal server error."})


def main() -> None:
    server = ThreadingHTTPServer(("127.0.0.1", PORT), ApiHandler)
    print(f"FIX Insight API listening on http://localhost:{PORT} (provider: {PROVIDER_NAME})")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.shutdown()


if __name__ == "__main__":
    main()
