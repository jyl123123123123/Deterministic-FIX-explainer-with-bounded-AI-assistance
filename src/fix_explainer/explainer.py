"""Bounded explanation built only from deterministic FIX facts."""

from collections.abc import Mapping, Sequence
from typing import Any, Protocol

from .message import ParsedFixMessage
from .models import ValidationError
from .spec import FixSpecification


class BoundedExplanationProvider(Protocol):
    """Optional provider interface that receives structured facts, never raw bytes."""

    def summarize(self, context: Mapping[str, object]) -> str:
        ...


def build_explanation_context(
    message: ParsedFixMessage,
    specification: FixSpecification | None = None,
    additional_errors: Sequence[ValidationError] = (),
) -> dict[str, Any]:
    """Build a traceable context suitable for deterministic or bounded AI output."""
    errors = (*message.errors, *additional_errors)
    message_spec = (
        specification.messages.get(message.message_type)
        if specification is not None and message.message_type is not None
        else None
    )
    known_facts: list[dict[str, object]] = [
        {
            "claim": f"FIX MsgType is {message.message_type!r}.",
            "evidence_tags": [35],
        }
    ] if message.message_type is not None else []
    if message_spec is not None:
        known_facts.append(
            {
                "claim": f"Message purpose is {message_spec.name}.",
                "evidence_tags": [35],
                "specification": specification.version if specification else None,
            }
        )

    for field in message.body:
        field_fact: dict[str, object] = {
            "tag": field.tag,
            "value": field.value,
            "evidence_tags": [field.tag],
        }
        if specification is not None and field.tag in specification.fields:
            field_fact["field_name"] = specification.fields[field.tag].name
        known_facts.append({"claim": "Field is present.", "field": field_fact})

    return {
        "known_facts": known_facts,
        "inferred_context": [],
        "unknowns": [
            "Business outcome and causality are not determined by this message alone."
        ],
        "validation_errors": [_error_to_dict(error) for error in errors],
    }


def explain_deterministically(
    message: ParsedFixMessage,
    specification: FixSpecification | None = None,
    additional_errors: Sequence[ValidationError] = (),
) -> dict[str, Any]:
    """Return a plain-language explanation without making unsupported inferences."""
    context = build_explanation_context(message, specification, additional_errors)
    if message.message_type is None:
        summary = "The message has no determinable FIX message type."
    elif context["validation_errors"]:
        summary = f"The FIX message is type {message.message_type!r} and has validation errors."
    else:
        summary = f"The FIX message is type {message.message_type!r} and passed available checks."
    return {"summary": summary, **context}


def explain_with_provider(
    message: ParsedFixMessage,
    provider: BoundedExplanationProvider,
    specification: FixSpecification | None = None,
    additional_errors: Sequence[ValidationError] = (),
) -> dict[str, Any]:
    """Ask an optional provider to summarize facts while preserving deterministic output."""
    context = build_explanation_context(message, specification, additional_errors)
    return {
        "deterministic": context,
        "provider_summary": provider.summarize(context),
    }


def _error_to_dict(error: ValidationError) -> dict[str, object]:
    return {
        "code": error.code,
        "message": error.message,
        "severity": error.severity,
        "tag": error.tag,
        "ordinal": error.ordinal,
    }