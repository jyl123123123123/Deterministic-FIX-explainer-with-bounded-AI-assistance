"""FIX wire-level BodyLength and CheckSum validation."""

from .message import ParsedFixMessage, split_message
from .models import FixField, ValidationError


def validate_body_length(
    payload: bytes,
    message: ParsedFixMessage,
    delimiter: bytes = b"\x01",
) -> ValidationError | None:
    """Validate tag 9 against the byte span before the first tag 10."""
    body_length_field = _first_field(message.fields, 9)
    checksum_field = _first_field(message.fields, 10)
    if body_length_field is None or checksum_field is None:
        return None

    try:
        declared_length = int(body_length_field.value)
    except ValueError:
        return ValidationError(
            code="INVALID_BODY_LENGTH",
            message="BodyLength tag 9 must contain an integer.",
            severity="error",
            tag=9,
            ordinal=body_length_field.ordinal,
        )

    body_start = body_length_field.end_offset + len(delimiter)
    actual_length = checksum_field.start_offset - body_start
    if declared_length != actual_length:
        return ValidationError(
            code="BODY_LENGTH_MISMATCH",
            message=(
                f"BodyLength declares {declared_length} bytes, "
                f"but {actual_length} bytes occur before CheckSum."
            ),
            severity="error",
            tag=9,
            ordinal=body_length_field.ordinal,
        )
    return None


def validate_checksum(
    payload: bytes,
    message: ParsedFixMessage,
) -> ValidationError | None:
    """Validate tag 10 against the modulo-256 sum of preceding payload bytes."""
    checksum_field = _first_field(message.fields, 10)
    if checksum_field is None:
        return None

    if len(checksum_field.value) != 3 or not checksum_field.value.isdigit():
        return ValidationError(
            code="INVALID_CHECKSUM",
            message="CheckSum tag 10 must contain exactly three digits.",
            severity="error",
            tag=10,
            ordinal=checksum_field.ordinal,
        )

    declared_checksum = int(checksum_field.value)
    actual_checksum = sum(payload[: checksum_field.start_offset]) % 256
    if declared_checksum != actual_checksum:
        return ValidationError(
            code="CHECKSUM_MISMATCH",
            message=(
                f"CheckSum declares {declared_checksum:03d}, "
                f"but calculated value is {actual_checksum:03d}."
            ),
            severity="error",
            tag=10,
            ordinal=checksum_field.ordinal,
        )
    return None


def validate_integrity(
    payload: bytes,
    message: ParsedFixMessage | None = None,
    delimiter: bytes = b"\x01",
) -> tuple[ValidationError, ...]:
    """Return deterministic BodyLength and CheckSum findings for a payload."""
    parsed = message if message is not None else split_message(payload, delimiter)
    errors: list[ValidationError] = []
    body_length_error = validate_body_length(payload, parsed, delimiter)
    if body_length_error is not None:
        errors.append(body_length_error)
    checksum_error = validate_checksum(payload, parsed)
    if checksum_error is not None:
        errors.append(checksum_error)
    return tuple(errors)


def _first_field(fields: tuple[FixField, ...], tag: int) -> FixField | None:
    return next((field for field in fields if field.tag == tag), None)