from fix_explainer import (
    EventType,
    TradingDataService,
    generate_synthetic_messages,
    normalize_fix_message,
)


def test_normalizer_emits_trade_only_for_execution_fields() -> None:
    messages = generate_synthetic_messages(1000)
    order = next(message for message in messages if message.message_type == "D")
    execution = next(message for message in messages if message.message_type == "8")

    assert normalize_fix_message(order.raw_message).event_type is EventType.ORDER_NEW
    execution_event = normalize_fix_message(execution.raw_message)
    assert execution_event is not None
    assert execution_event.event_type in {
        EventType.TRADE,
        EventType.ORDER_REJECTED,
        EventType.ORDER_CANCELED,
        EventType.STATUS,
    }


def test_trading_service_exposes_aggregated_snapshot() -> None:
    service = TradingDataService()
    try:
        for message in generate_synthetic_messages(1000):
            service.ingest(message)
        snapshot = service.snapshot()
        assert snapshot["processed"] == 1000
        assert snapshot["orders"] > 0
        assert snapshot["flow"]["buy_volume"] + snapshot["flow"]["sell_volume"] > 0
        assert snapshot["recent_events"]
    finally:
        service.close()
