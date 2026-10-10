"""Deterministic message validation against a loaded FIX specification."""

from .message import ParsedFixMessage
from .models import ValidationError
from .spec import FixSpecification, MessageSpec


def validate_message_schema(
    message: ParsedFixMessage,
    specification: FixSpecification,
) -> tuple[ValidationError, ...]:
    """Validate MsgType, required fields, and declared enum values."""
    if message.message_type is None:
        return ()

    message_spec = specification.messages.get(message.message_type)
    if message_spec is None:
        return (
            ValidationError(
                code="UNKNOWN_MSG_TYPE",
                message=f"No specification is loaded for MsgType {message.message_type!r}.",
                severity="error",
                tag=35,
            ),
        )

    errors: list[ValidationError] = []
    fields_by_tag = {field.tag: field for field in message.fields}
    for tag in sorted(message_spec.required_fields):
        if tag not in fields_by_tag:
            errors.append(
                ValidationError(
                    code="MISSING_REQUIRED_TAG",
                    message=f"Required tag {tag} is missing for MsgType {message.message_type}.",
                    severity="error",
                    tag=tag,
                )
            )

    for field in message.body:
        field_spec = specification.fields.get(field.tag)
        if field_spec is None:
            continue
        if field_spec.enum_values and field.value not in field_spec.enum_values:
            errors.append(
                ValidationError(
                    code="INVALID_ENUM_VALUE",
                    message=(
                        f"Value {field.value!r} is not valid for tag {field.tag} "
                        f"({field_spec.name})."
                    ),
                    severity="error",
                    tag=field.tag,
                    ordinal=field.ordinal,
                )
            )
    return tuple(errors)