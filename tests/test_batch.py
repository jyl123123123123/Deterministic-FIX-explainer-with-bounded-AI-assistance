from fix_explainer import generate_synthetic_messages, parse_batch


def test_parse_batch_processes_synthetic_messages_and_preserves_sequence() -> None:
    messages = generate_synthetic_messages(1000)

    result = parse_batch(message.raw_message for message in messages)

    assert len(result.items) == 1000
    assert result.accepted == 1000
    assert result.rejected == 0
    assert [item.sequence for item in result.items] == list(range(1, 1001))
    assert result.items[0].parsed.message_type == "D"


def test_parse_batch_isolates_invalid_message() -> None:
    messages = generate_synthetic_messages(1000)
    payloads = [messages[0].raw_message, b"broken", messages[1].raw_message]

    result = parse_batch(payloads)

    assert result.accepted == 2
    assert result.rejected == 1
    assert result.items[1].sequence == 2
    assert result.items[1].parsed.message_type is None
    assert "MALFORMED_FIELD" in {error.code for error in result.items[1].errors}
    assert result.items[2].sequence == 3
    assert result.items[2].parsed.message_type == "8"


def test_parse_batch_rejects_more_than_configured_limit() -> None:
    messages = generate_synthetic_messages(1000)

    try:
        parse_batch((message.raw_message for message in messages), max_batch_size=999)
    except ValueError as error:
        assert "more than 999" in str(error)
    else:
        raise AssertionError("a batch larger than its limit should be rejected")

    try:
        parse_batch((message.raw_message for message in messages), max_batch_size=2001)
    except ValueError as error:
        assert "between 1 and 2000" in str(error)
    else:
        raise AssertionError("an invalid batch size should be rejected")
