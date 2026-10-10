from datetime import datetime, timezone
from decimal import Decimal

import pytest

from fix_explainer import EventSource, EventType, FixTag, Side, TradingEvent


def test_trading_event_matches_shared_trade_contract() -> None:
    event = TradingEvent(
        event_id="EXEC-001",
        timestamp=datetime(2026, 10, 10, 17, 0, tzinfo=timezone.utc),
        symbol="AAPL",
        side=Side.BUY,
        event_type=EventType.TRADE,
        last_qty=100,
        last_px=Decimal("185.50"),
        order_id="ORD-001",
        cl_ord_id="CLI-001",
        exec_id="EXEC-001",
        cum_qty=100,
        leaves_qty=0,
        source=EventSource.SIMULATED,
    )

    assert event.to_dict() == {
        "event_id": "EXEC-001",
        "timestamp": "2026-10-10T17:00:00.000Z",
        "symbol": "AAPL",
        "side": "BUY",
        "event_type": "TRADE",
        "last_qty": 100,
        "last_px": 185.5,
        "order_id": "ORD-001",
        "cl_ord_id": "CLI-001",
        "exec_id": "EXEC-001",
        "cum_qty": 100,
        "leaves_qty": 0,
        "order_status": None,
        "source": "SIMULATED",
    }


def test_trade_requires_confirmed_execution_values() -> None:
    with pytest.raises(ValueError, match="TRADE requires"):
        TradingEvent(
            event_id="EXEC-002",
            timestamp=datetime.now(timezone.utc),
            symbol="MSFT",
            side=Side.SELL,
            event_type=EventType.TRADE,
            last_qty=0,
            last_px=None,
            order_id="ORD-002",
            source=EventSource.SIMULATED,
        )


def test_non_trade_event_can_omit_execution_values() -> None:
    event = TradingEvent(
        event_id="ORD-003",
        timestamp=datetime.now(timezone.utc),
        symbol="NVDA",
        side=Side.BUY,
        event_type=EventType.ORDER_NEW,
        last_qty=None,
        last_px=None,
        order_id="ORD-003",
        source=EventSource.SIMULATED,
    )

    assert event.to_dict()["event_type"] == "ORDER_NEW"
    assert event.to_dict()["last_qty"] is None


def test_fix_tag_mapping_covers_correlation_and_execution_fields() -> None:
    assert FixTag.CL_ORD_ID == 11
    assert FixTag.ORDER_ID == 37
    assert FixTag.EXEC_ID == 17
    assert FixTag.LAST_QTY == 32
    assert FixTag.LAST_PX == 31
    assert FixTag.EXEC_TYPE == 150
