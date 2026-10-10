"""Structural FIX message parsing built on top of the byte tokenizer."""

from dataclasses import dataclass

from .models import FixField, ValidationError
from .tokenizer import tokenize

HEADER_TAGS = frozenset(
    {
        8,
        9,
        35,
        34,
        43,
        49,
        50,
        52,
        56,
        57,
        97,
        115,
        116,
        128,
        129,
        142,
        143,
        144,
        145,
        369,
        1128,
        1129,
    }
)
TRAILER_TAGS = frozenset({10, 89, 93})


@dataclass(frozen=True)
class ParsedFixMessage:
    """A FIX message with ordered fields divided into protocol sections."""

    fields: tuple[FixField, ...]
    header: tuple[FixField, ...]
    body: tuple[FixField, ...]
    trailer: tuple[FixField, ...]
    message_type: str | None
    errors: tuple[ValidationError, ...]


def split_message(payload: bytes, delimiter: bytes = b"\x01") -> ParsedFixMessage:
    """Tokenize a payload and divide its fields into Header, Body, and Trailer."""
    tokenized = tokenize(payload, delimiter)
    header: list[FixField] = []
    body: list[FixField] = []
    trailer: list[FixField] = []
    errors = list(tokenized.errors)
    in_body = False
    in_trailer = False

    for field in tokenized.fields:
        if in_trailer:
            trailer.append(field)
            if field.tag not in TRAILER_TAGS:
                errors.append(
                    ValidationError(
                        code="FIELD_AFTER_CHECKSUM",
                        message="Only trailer fields may follow tag 10.",
                        severity="error",
                        tag=field.tag,
                        ordinal=field.ordinal,
                    )
                )
        elif field.tag == 10:
            in_trailer = True
            trailer.append(field)
        elif not in_body and field.tag in HEADER_TAGS:
            header.append(field)
        else:
            in_body = True
            body.append(field)

    fields_by_tag = {field.tag for field in tokenized.fields}
    for tag, code, message in (
        (8, "MISSING_BEGIN_STRING", "BeginString tag 8 is missing."),
        (9, "MISSING_BODY_LENGTH", "BodyLength tag 9 is missing."),
        (35, "MISSING_MSG_TYPE", "MsgType tag 35 is missing."),
        (10, "MISSING_CHECKSUM", "CheckSum tag 10 is missing."),
    ):
        if tag not in fields_by_tag:
            errors.append(
                ValidationError(code=code, message=message, severity="error", tag=tag)
            )

    message_type = next(
        (field.value for field in header if field.tag == 35),
        None,
    )
    return ParsedFixMessage(
        fields=tokenized.fields,
        header=tuple(header),
        body=tuple(body),
        trailer=tuple(trailer),
        message_type=message_type,
        errors=tuple(errors),
    )