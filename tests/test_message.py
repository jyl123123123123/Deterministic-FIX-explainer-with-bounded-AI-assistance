from fix_explainer import split_message


def test_split_message_preserves_sections_and_message_type() -> None:
    payload = b"8=FIX.4.4\x019=20\x0135=D\x0149=SENDER\x0111=ABC\x0154=1\x0110=000\x01"

    message = split_message(payload)

    assert [field.tag for field in message.header] == [8, 9, 35, 49]
    assert [field.tag for field in message.body] == [11, 54]
    assert [field.tag for field in message.trailer] == [10]
    assert message.message_type == "D"
    assert message.errors == ()


def test_split_message_keeps_duplicate_body_tags_in_order() -> None:
    payload = b"8=FIX.4.4\x019=10\x0135=D\x0111=ONE\x0111=TWO\x0110=000\x01"

    message = split_message(payload)

    assert [(field.tag, field.value) for field in message.body] == [
        (11, "ONE"),
        (11, "TWO"),
    ]


def test_split_message_reports_fields_after_checksum() -> None:
    payload = b"8=FIX.4.4\x019=5\x0135=D\x0110=000\x0149=TOO_LATE\x01"

    message = split_message(payload)

    assert [field.tag for field in message.trailer] == [10, 49]
    assert [error.code for error in message.errors] == ["FIELD_AFTER_CHECKSUM"]


def test_split_message_reports_missing_structural_tags() -> None:
    message = split_message(b"11=ABC\x01")

    assert [error.code for error in message.errors] == [
        "MISSING_BEGIN_STRING",
        "MISSING_BODY_LENGTH",
        "MISSING_MSG_TYPE",
        "MISSING_CHECKSUM",
    ]