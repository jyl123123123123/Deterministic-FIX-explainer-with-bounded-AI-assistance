from fix_explainer import FixField, ValidationError


def test_fix_field_preserves_value_and_source_metadata() -> None:
    field = FixField(
        tag=35,
        value="D",
        raw_value=b"D",
        ordinal=2,
        start_offset=12,
        end_offset=16,
    )

    assert field.tag == 35
    assert field.value == "D"
    assert field.raw_value == b"D"
    assert field.ordinal == 2
    assert field.start_offset == 12
    assert field.end_offset == 16


def test_fix_field_is_immutable() -> None:
    field = FixField(35, "D", b"D", 0, 0, 4)

    try:
        field.value = "8"  # type: ignore[misc]
    except AttributeError:
        pass
    else:
        raise AssertionError("FixField must be immutable")


def test_validation_error_can_point_to_a_field() -> None:
    finding = ValidationError(
        code="MISSING_REQUIRED_TAG",
        message="Required tag 11 is missing.",
        severity="error",
        tag=11,
        ordinal=None,
    )

    assert finding.code == "MISSING_REQUIRED_TAG"
    assert finding.severity == "error"
    assert finding.tag == 11
    assert finding.ordinal is None


def test_validation_error_defaults_to_message_level_location() -> None:
    finding = ValidationError(
        code="INVALID_CHECKSUM",
        message="Checksum does not match.",
        severity="error",
    )

    assert finding.tag is None
    assert finding.ordinal is None