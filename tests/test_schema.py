from pathlib import Path

from fix_explainer import load_orchestra, split_message, validate_message_schema


FIXTURE_PATH = Path(__file__).parent / "fixtures" / "new_order_single.fix"
SPEC_PATH = Path(__file__).parent / "fixtures" / "fix_orchestra_subset.xml"


def load_valid_message():
    return split_message(FIXTURE_PATH.read_bytes().rstrip(b"\r\n").replace(b"|", b"\x01"))


def test_schema_accepts_message_with_all_required_fields() -> None:
    message = load_valid_message()
    specification = load_orchestra(SPEC_PATH)

    assert validate_message_schema(message, specification) == ()


def test_schema_reports_missing_required_field() -> None:
    payload = FIXTURE_PATH.read_bytes().replace(b"11=ORDER-1|", b"").replace(b"|", b"\x01")
    message = split_message(payload)
    specification = load_orchestra(SPEC_PATH)

    errors = validate_message_schema(message, specification)

    assert [error.code for error in errors] == ["MISSING_REQUIRED_TAG"]
    assert errors[0].tag == 11


def test_schema_reports_invalid_enum_value() -> None:
    payload = FIXTURE_PATH.read_bytes().replace(b"54=1|", b"54=9|").replace(b"|", b"\x01")
    message = split_message(payload)
    specification = load_orchestra(SPEC_PATH)

    errors = validate_message_schema(message, specification)

    assert [error.code for error in errors] == ["INVALID_ENUM_VALUE"]
    assert errors[0].tag == 54


def test_schema_reports_unknown_message_type() -> None:
    payload = FIXTURE_PATH.read_bytes().replace(b"35=D|", b"35=Z|").replace(b"|", b"\x01")
    message = split_message(payload)
    specification = load_orchestra(SPEC_PATH)

    errors = validate_message_schema(message, specification)

    assert [error.code for error in errors] == ["UNKNOWN_MSG_TYPE"]