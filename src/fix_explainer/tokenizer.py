"""Tokenizer for the tag-value wire format used by FIX messages."""

from dataclasses import dataclass

from .models import FixField, ValidationError


@dataclass(frozen=True)
class TokenizationResult:
    """Fields and syntax findings produced from one FIX payload."""

    fields: tuple[FixField, ...]
    errors: tuple[ValidationError, ...]


def tokenize(payload: bytes, delimiter: bytes = b"\x01") -> TokenizationResult:
    """Split a FIX payload into ordered fields without interpreting its tags."""
    if len(delimiter) != 1:
        raise ValueError("delimiter must be exactly one byte")

    fields: list[FixField] = []
    errors: list[ValidationError] = []
    delimiter_value = delimiter[0]
    start = 0
    ordinal = 0

    while start < len(payload):
        delimiter_position = payload.find(delimiter, start)
        if delimiter_position == -1:
            token_end = len(payload)
            has_delimiter = False
        else:
            token_end = delimiter_position
            has_delimiter = True

        token = payload[start:token_end]
        equals_position = token.find(b"=")
        if equals_position <= 0:
            errors.append(
                ValidationError(
                    code="MALFORMED_FIELD",
                    message="Field must contain a non-empty tag followed by '='.",
                    severity="error",
                    ordinal=ordinal,
                )
            )
        else:
            raw_tag = token[:equals_position]
            raw_value = token[equals_position + 1 :]
            try:
                tag = int(raw_tag.decode("ascii"))
            except (UnicodeDecodeError, ValueError):
                errors.append(
                    ValidationError(
                        code="INVALID_TAG",
                        message="Tag must contain only ASCII digits.",
                        severity="error",
                        ordinal=ordinal,
                    )
                )
            else:
                if tag <= 0:
                    errors.append(
                        ValidationError(
                            code="INVALID_TAG",
                            message="Tag must be a positive integer.",
                            severity="error",
                            ordinal=ordinal,
                        )
                    )
                else:
                    try:
                        value = raw_value.decode("ascii")
                    except UnicodeDecodeError:
                        value = raw_value.decode("ascii", errors="replace")
                        errors.append(
                            ValidationError(
                                code="INVALID_VALUE_ENCODING",
                                message="Field value must contain ASCII bytes.",
                                severity="error",
                                tag=tag,
                                ordinal=ordinal,
                            )
                        )

                    fields.append(
                        FixField(
                            tag=tag,
                            value=value,
                            raw_value=raw_value,
                            ordinal=ordinal,
                            start_offset=start,
                            end_offset=token_end,
                        )
                    )

        ordinal += 1
        if not has_delimiter:
            errors.append(
                ValidationError(
                    code="MISSING_DELIMITER",
                    message=f"Field must end with delimiter byte {delimiter_value}.",
                    severity="error",
                    ordinal=ordinal - 1,
                )
            )
            break
        start = token_end + 1

    return TokenizationResult(tuple(fields), tuple(errors))