"""Deterministic JSON serialization for parsed FIX messages."""

import json
from collections.abc import Iterable
from typing import Any

from .message import ParsedFixMessage
from .models import FixField, ValidationError


def message_to_dict(
    message: ParsedFixMessage,
    additional_errors: Iterable[ValidationError] = (),
) -> dict[str, Any]:
    """Convert a parsed message into a JSON-compatible deterministic mapping."""
    errors = (*message.errors, *tuple(additional_errors))
    return {
        "message_type": message.message_type,
        "fields": [_field_to_dict(field) for field in message.fields],
        "header": [_field_to_dict(field) for field in message.header],
        "body": [_field_to_dict(field) for field in message.body],
        "trailer": [_field_to_dict(field) for field in message.trailer],
        "errors": [_error_to_dict(error) for error in errors],
    }


def message_to_json(
    message: ParsedFixMessage,
    additional_errors: Iterable[ValidationError] = (),
) -> str:
    """Serialize a parsed message using stable key ordering and compact JSON."""
    return json.dumps(
        message_to_dict(message, additional_errors),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _field_to_dict(field: FixField) -> dict[str, Any]:
    return {
        "tag": field.tag,
        "value": field.value,
        "raw_value_hex": field.raw_value.hex(),
        "ordinal": field.ordinal,
        "start_offset": field.start_offset,
        "end_offset": field.end_offset,
    }


def _error_to_dict(error: ValidationError) -> dict[str, Any]:
    return {
        "code": error.code,
        "message": error.message,
        "severity": error.severity,
        "tag": error.tag,
        "ordinal": error.ordinal,
    }