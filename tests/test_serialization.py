import json
from pathlib import Path

from fix_explainer import message_to_dict, message_to_json, split_message
from fix_explainer.models import ValidationError


FIXTURE_PATH = Path(__file__).parent / "fixtures" / "new_order_single.fix"


def load_message():
    payload = FIXTURE_PATH.read_bytes().rstrip(b"\r\n").replace(b"|", b"\x01")
    return split_message(payload)


def test_message_to_dict_preserves_sections_and_duplicate_safe_lists() -> None:
    result = message_to_dict(load_message())

    assert result["message_type"] == "D"
    assert [field["tag"] for field in result["fields"]] == [
        8,
        9,
        35,
        49,
        56,
        11,
        55,
        54,
        38,
        40,
        44,
        10,
    ]
    assert [field["tag"] for field in result["header"]] == [8, 9, 35, 49, 56]
    assert result["errors"] == []


def test_message_to_json_is_parseable_and_includes_additional_errors() -> None:
    extra_error = ValidationError(
        code="CHECKSUM_MISMATCH",
        message="Checksum does not match.",
        severity="error",
        tag=10,
        ordinal=11,
    )

    serialized = message_to_json(load_message(), [extra_error])
    result = json.loads(serialized)

    assert result["body"][0]["raw_value_hex"] == "4f524445522d31"
    assert result["errors"] == [
        {
            "code": "CHECKSUM_MISMATCH",
            "message": "Checksum does not match.",
            "ordinal": 11,
            "severity": "error",
            "tag": 10,
        }
    ]