from pathlib import Path

from fix_explainer import split_message, validate_integrity


FIXTURE_PATH = Path(__file__).parent / "fixtures" / "new_order_single.fix"


def load_fixture() -> bytes:
    readable_fixture = FIXTURE_PATH.read_bytes().rstrip(b"\r\n")
    return readable_fixture.replace(b"|", b"\x01")


def test_new_order_single_fixture_round_trips_through_deterministic_pipeline() -> None:
    payload = load_fixture()
    message = split_message(payload)

    assert len(message.fields) == 12
    assert message.message_type == "D"
    assert [field.tag for field in message.header] == [8, 9, 35, 49, 56]
    assert [field.tag for field in message.body] == [11, 55, 54, 38, 40, 44]
    assert [field.tag for field in message.trailer] == [10]
    assert message.errors == ()
    assert validate_integrity(payload, message) == ()


def test_new_order_single_fixture_keeps_business_values() -> None:
    message = split_message(load_fixture())

    assert [(field.tag, field.value) for field in message.fields] == [
        (8, "FIX.4.4"),
        (9, "73"),
        (35, "D"),
        (49, "CLIENT12"),
        (56, "BROKER"),
        (11, "ORDER-1"),
        (55, "AAPL"),
        (54, "1"),
        (38, "100"),
        (40, "2"),
        (44, "150.25"),
        (10, "030"),
    ]