from fix_explainer import split_message, validate_integrity


def make_message(body: bytes = b"35=D\x0111=ABC\x01") -> bytes:
    prefix = b"8=FIX.4.4\x019=" + str(len(body)).encode("ascii") + b"\x01" + body
    checksum = f"{sum(prefix) % 256:03d}".encode("ascii")
    return prefix + b"10=" + checksum + b"\x01"


def test_integrity_accepts_valid_body_length_and_checksum() -> None:
    payload = make_message()

    assert validate_integrity(payload, split_message(payload)) == ()


def test_integrity_reports_body_length_mismatch() -> None:
    payload = make_message().replace(b"9=12\x01", b"9=10\x01")

    errors = validate_integrity(payload)

    assert [error.code for error in errors] == [
        "BODY_LENGTH_MISMATCH",
        "CHECKSUM_MISMATCH",
    ]


def test_integrity_reports_checksum_mismatch() -> None:
    payload = make_message()[:-7] + b"10=000\x01"

    errors = validate_integrity(payload)

    assert [error.code for error in errors] == ["CHECKSUM_MISMATCH"]


def test_integrity_reports_non_numeric_checksum() -> None:
    payload = make_message()[:-7] + b"10=ABC\x01"

    errors = validate_integrity(payload)

    assert [error.code for error in errors] == ["INVALID_CHECKSUM"]