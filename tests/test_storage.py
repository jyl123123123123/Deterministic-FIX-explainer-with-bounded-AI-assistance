from datetime import datetime, timezone
from decimal import Decimal

from fix_explainer import (
    EventSource,
    EventType,
    OrderStatus,
    Side,
    SQLiteTradingRepository,
    TradingEvent,
)


def trade_event(
    *,
    exec_id: str = "EXEC-001",
    cl_ord_id: str = "CLI-001",
    cum_qty: int = 100,
    leaves_qty: int = 0,
) -> TradingEvent:
    return TradingEvent(
        event_id=exec_id,
        timestamp=datetime(2026, 10, 10, 17, 0, tzinfo=timezone.utc),
        symbol="AAPL",
        side=Side.BUY,
        event_type=EventType.TRADE,
        last_qty=100,
        last_px=Decimal("185.50"),
        order_id="ORD-001",
        cl_ord_id=cl_ord_id,
        exec_id=exec_id,
        cum_qty=cum_qty,
        leaves_qty=leaves_qty,
        order_status=OrderStatus.FILLED,
        source=EventSource.SIMULATED,
    )


def test_repository_creates_run_and_persists_raw_message() -> None:
    with SQLiteTradingRepository() as repository:
        repository.create_run("run-1", 7, 1000, 25)
        message_id = repository.save_message(
            run_id="run-1",
            sequence=1,
            raw_message=b"8=FIX.4.4\x01",
            message_type="D",
            accepted=True,
        )

        assert message_id == 1
        assert repository.get_run("run-1")["status"] == "PENDING"


def test_repository_deduplicates_execution_by_exec_id() -> None:
    with SQLiteTradingRepository() as repository:
        event = trade_event()
        repository.upsert_order(event, order_qty=100)

        assert repository.save_execution(event) is True
        assert repository.save_execution(event) is False
        assert len(repository.list_executions()) == 1
        assert repository.list_orders()[0]["cum_qty"] == 100


def test_repository_rejects_invalid_run_configuration() -> None:
    with SQLiteTradingRepository() as repository:
        try:
            repository.create_run("bad-run", 1, 999, 25)
        except Exception as error:
            assert "CHECK constraint" in str(error)
        else:
            raise AssertionError("invalid run configuration should be rejected")
