"""Local, fixed-template explanations. No network or model dependencies."""

import json
from collections.abc import Mapping

# This is a disclosure policy, not a FIX dictionary. Unknown tags fail closed.
DEFAULT_ALLOWED_TAGS = frozenset({35, 38, 40, 44, 54, 55, 59, 150, 39, 151, 14, 6})
SENSITIVE_TAGS = frozenset({1, 11, 37, 41, 49, 50, 56, 57, 115, 116, 128,
                            129, 142, 143, 144, 145, 448, 523, 553, 554, 790})


KNOWN_ERROR_CODES = frozenset({
    "INVALID_BODY_LENGTH", "BODY_LENGTH_MISMATCH", "INVALID_CHECKSUM",
    "CHECKSUM_MISMATCH", "MALFORMED_FIELD", "INVALID_TAG",
    "INVALID_VALUE_ENCODING", "MISSING_DELIMITER", "FIELD_AFTER_CHECKSUM",
    "MISSING_BEGIN_STRING", "MISSING_BODY_LENGTH", "MISSING_MSG_TYPE",
    "MISSING_CHECKSUM", "UNKNOWN_MSG_TYPE", "MISSING_REQUIRED_TAG", "INVALID_ENUM_VALUE",
})


def _quoted(value: object) -> str:
    # Escape untrusted field text, including newlines and citation-like content.
    return json.dumps(str(value), ensure_ascii=True)


def _source(tag: int, ordinal: object) -> str:
    if type(ordinal) is int and ordinal >= 0:
        return f"[tag={tag}; ordinal={ordinal}]"
    return f"[tag={tag}; occurrence unavailable]"


class TemplateExplanationProvider:
    """Render only supplied facts. Input is never mutated.

    Ordinals are zero-based token positions, not repeating-group paths.
    Custom allowlists can only narrow the default disclosure policy.
    """

    def __init__(self, allowed_tags=DEFAULT_ALLOWED_TAGS):
        self.allowed_tags = frozenset(allowed_tags) & DEFAULT_ALLOWED_TAGS

    def summarize(self, context: Mapping[str, object]) -> str:
        lines = []
        for index, fact in enumerate(context.get("known_facts", [])):
            field = fact.get("field")
            if field is not None:
                tag = field["tag"]
                cite = _source(tag, field.get("ordinal"))
                if tag in SENSITIVE_TAGS:
                    lines.append(f"Identifier value withheld. {cite}")
                elif tag in self.allowed_tags:
                    name = _quoted(field.get("field_name", f"Tag {tag}"))
                    value = _quoted(field["value"])
                    enum = (f" (specification label {_quoted(field['enum_name'])})"
                            if "enum_name" in field else "")
                    lines.append(f"Field {name} has value {value}{enum}. {cite}")
                continue
            # Only the two established claim shapes are accepted; never interpret enums.
            claim = fact.get("claim", "")
            if fact.get("evidence_tags") == [35] and (
                claim.startswith("FIX MsgType is ") or
                claim.startswith("Message purpose is ")
            ):
                sources = fact.get("evidence_fields", [])
                cite = (_source(35, sources[0].get("ordinal")) if sources
                        else _source(35, None))
                lines.append(f"Supplied fact: {_quoted(claim)} {cite} [known_facts[{index}]]")
        for index, error in enumerate(context.get("validation_errors", [])):
            # Free-form diagnostic text could echo identifiers. Original remains in
            # deterministic.validation_errors; summary deliberately withholds it.
            cite = (f" {_source(error['tag'], error.get('ordinal'))}"
                    if type(error.get("tag")) is int else "")
            code = error.get("code")
            label = code if code in KNOWN_ERROR_CODES else "unlisted diagnostic"
            lines.append(f"Validation finding {_quoted(label)} ({_quoted(error['severity'])}); "
                         f"diagnostic text withheld.{cite} [validation_errors[{index}]]")
        for index, unknown in enumerate(context.get("unknowns", [])):
            if unknown == "Business outcome and causality are not determined by this message alone.":
                lines.append(f"{unknown} [unknowns[{index}]]")
            else:
                lines.append(f"Additional uncertainty recorded; text withheld. [unknowns[{index}]]")
        return "\n".join(lines) or "No disclosable explanation facts were supplied."
