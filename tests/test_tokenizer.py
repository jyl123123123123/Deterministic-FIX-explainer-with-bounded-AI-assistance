from fix_explainer import tokenize


def test_tokenizer_preserves_order_duplicates_and_offsets() -> None:
    result = tokenize(b"35=D\x0111=ABC\x0111=XYZ\x01")

    assert [(field.tag, field.value) for field in result.fields] == [
        (35, "D"),
        (11, "ABC"),
        (11, "XYZ"),
    ]
    assert [(field.start_offset, field.end_offset) for field in result.fields] == [
        (0, 4),
        (5, 11),
        (12, 18),
    ]
    assert result.errors == ()


def test_tokenizer_reports_malformed_field_and_keeps_following_fields() -> None:
    result = tokenize(b"35=D\x01broken\x0111=ABC\x01")

    assert [(field.tag, field.value) for field in result.fields] == [(35, "D"), (11, "ABC")]
    assert [error.code for error in result.errors] == ["MALFORMED_FIELD"]
    assert result.errors[0].ordinal == 1


def test_tokenizer_reports_invalid_tag_and_missing_delimiter() -> None:
    result = tokenize(b"x=D\x0111=ABC")

    assert [(field.tag, field.value) for field in result.fields] == [(11, "ABC")]
    assert [error.code for error in result.errors] == [
        "INVALID_TAG",
        "MISSING_DELIMITER",
    ]


def test_tokenizer_rejects_multibyte_delimiter() -> None:
    try:
        tokenize(b"35=D", delimiter=b"||")
    except ValueError as error:
        assert str(error) == "delimiter must be exactly one byte"
    else:
        raise AssertionError("tokenizer must reject a multibyte delimiter")