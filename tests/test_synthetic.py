from fix_explainer import (
    generate_synthetic_messages,
    split_message,
    validate_integrity,
)


def test_generator_is_reproducible_and_time_ordered() -> None:
    first = generate_synthetic_messages(1000, seed=7)
    second = generate_synthetic_messages(1000, seed=7)

    assert [message.raw_message for message in first] == [
        message.raw_message for message in second
    ]
    assert len(first) == 1000
    assert [message.sequence for message in first] == list(range(1, 1001))
    assert [message.timestamp for message in first] == sorted(
        message.timestamp for message in first
    )


def test_dataset_covers_required_lifecycles_and_valid_fix_integrity() -> None:
    messages = generate_synthetic_messages(1500)
    scenarios = {message.scenario for message in messages}
    duplicate_count = sum(message.is_duplicate for message in messages)

    assert {"FULL_FILL", "PARTIAL_FILL", "CANCEL", "REJECT", "CANCEL_REJECT"} <= scenarios
    assert {message.raw_message.split(b"35=", 1)[1][0:1] for message in messages} >= {
        b"D",
        b"8",
        b"F",
        b"9",
    }
    assert duplicate_count > 0
    for message in messages[:50]:
        parsed = split_message(message.raw_message)
        assert validate_integrity(message.raw_message, parsed) == ()


def test_generator_rejects_counts_outside_product_bounds() -> None:
    for count in (999, 2001):
        try:
            generate_synthetic_messages(count)
        except ValueError:
            continue
        raise AssertionError("count outside 1000-2000 must be rejected")
