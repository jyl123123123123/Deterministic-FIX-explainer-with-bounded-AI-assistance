from datetime import datetime, timezone
from decimal import Decimal

from fix_explainer import (
    EventSource,
    EventType,
    OrderCorrelator,
    OrderStatus,
    Side,
    TradingEvent,
)


def event(
    event_type: EventType,
    *,
    event_id: str,
    cl_ord_id: str | None = "CLI-001",
    order_id: str | None = "ORD-001",
    exec_id: str | None = None,
    quantity: int | None = None,
    price: str | None = None,
) -> TradingEvent:
    return TradingEvent(
        event_id=event_id,
        timestamp=datetime(2026, 10, 10, 17, 0, tzinfo=timezone.utc),
        symbol="AAPL",
        side=Side.BUY,
        event_type=event_type,
        last_qty=quantity,
        last_px=Decimal(price) if price else None,
        order_id=order_id,
        cl_ord_id=cl_ord_id,
        exec_id=exec_id,
        source=EventSource.SIMULATED,
    )


def test_correlator_matches_by_cl_ord_id_and_accumulates_partial_fills() -> None:
    correlator = OrderCorrelator()
    created = correlator.apply(
        event(EventType.ORDER_NEW, event_id="ORDER-001"), order_qty=100
    )
    first = correlator.apply(
        event(
            EventType.TRADE,
            event_id="EXEC-001",
            exec_id="EXEC-001",
            quantity=40,
            price="185.50",
        )
    )
    first_status = first.order.status
    second = correlator.apply(
        event(
            EventType.TRADE,
            event_id="EXEC-002",
            exec_id="EXEC-002",
            quantity=60,
            price="186.00",
        )
    )

    assert created.accepted is True
    assert first_status is OrderStatus.PARTIALLY_FILLED
    assert second.order.status is OrderStatus.FILLED
    assert second.order.cum_qty == 100
    assert second.order.leaves_qty == 0


def test_correlator_does_not_count_duplicate_or_overfill_execution() -> None:
    correlator = OrderCorrelator()
    correlator.apply(event(EventType.ORDER_NEW, event_id="ORDER-001"), order_qty=100)
    trade = event(
        EventType.TRADE,
        event_id="EXEC-001",
        exec_id="EXEC-001",
        quantity=100,
        price="185.50",
    )
    assert correlator.apply(trade).accepted is True
    duplicate = correlator.apply(trade)
    assert duplicate.accepted is True
    assert duplicate.duplicate is True
    assert duplicate.order.cum_qty == 100

    overfill = correlator.apply(
        event(
            EventType.TRADE,
            event_id="EXEC-002",
            exec_id="EXEC-002",
            quantity=1,
            price="185.50",
        )
    )
    assert overfill.accepted is False
    assert overfill.reason == "INVALID_TERMINAL_STATE_TRANSITION"


def test_correlator_rejects_unmatched_and_invalid_transitions() -> None:
    correlator = OrderCorrelator()
    unmatched = correlator.apply(
        event(
            EventType.TRADE,
            event_id="EXEC-404",
            cl_ord_id="UNKNOWN",
            exec_id="EXEC-404",
            quantity=10,
            price="10",
        )
    )
    assert unmatched.reason == "UNMATCHED_ORDER"

    correlator.apply(event(EventType.ORDER_NEW, event_id="ORDER-001"), order_qty=100)
    correlator.apply(
        event(
            EventType.TRADE,
            event_id="EXEC-001",
            exec_id="EXEC-001",
            quantity=100,
            price="185.50",
        )
    )
    canceled = correlator.apply(
        event(EventType.ORDER_CANCELED, event_id="CANCEL-001")
    )
    assert canceled.accepted is False
    assert canceled.reason == "INVALID_STATUS_TRANSITION"
