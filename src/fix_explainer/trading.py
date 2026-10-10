"""Integrated trading-flow service and normalized event conversion."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from .correlation import OrderCorrelator
from .events import EventSource, EventType, FixTag, OrderStatus, Side, TradingEvent
from .message import ParsedFixMessage, split_message
from .storage import SQLiteTradingRepository
from .synthetic import SyntheticMessage


def _tags(message: ParsedFixMessage) -> dict[int, str]:
    return {field.tag: field.value for field in message.fields}


def _timestamp(value: str | None) -> datetime:
    if value:
        try:
            return datetime.strptime(value, "%Y%m%d-%H:%M:%S").replace(tzinfo=timezone.utc)
        except ValueError:
            pass
    return datetime.now(timezone.utc)


def normalize_fix_message(
    payload: bytes,
    *,
    source: EventSource = EventSource.SIMULATED,
) -> TradingEvent | None:
    """Convert a valid business FIX message into one consumer-facing event."""
    parsed = split_message(payload)
    tags = _tags(parsed)
    message_type = tags.get(FixTag.MESSAGE_TYPE)
    side = Side.BUY if tags.get(FixTag.SIDE) == "1" else Side.SELL
    cl_ord_id = tags.get(FixTag.CL_ORD_ID)
    order_id = tags.get(FixTag.ORDER_ID)
    symbol = tags.get(FixTag.SYMBOL, "UNKNOWN")
    if message_type == "D":
        return TradingEvent(
            event_id=cl_ord_id or f"ORDER-{tags.get(34, 'UNKNOWN')}",
            timestamp=_timestamp(tags.get(52)),
            symbol=symbol,
            side=side,
            event_type=EventType.ORDER_NEW,
            last_qty=None,
            last_px=None,
            order_id=order_id,
            cl_ord_id=cl_ord_id,
            source=source,
        )
    if message_type == "F":
        return TradingEvent(
            event_id=cl_ord_id or f"CANCEL-{tags.get(34, 'UNKNOWN')}",
            timestamp=_timestamp(tags.get(52)),
            symbol=symbol,
            side=side,
            event_type=EventType.ORDER_CANCELED,
            last_qty=None,
            last_px=None,
            order_id=order_id,
            cl_ord_id=cl_ord_id,
            order_status=OrderStatus.CANCELED,
            source=source,
        )
    if message_type == "9":
        return TradingEvent(
            event_id=tags.get(FixTag.EXEC_ID, f"CANCEL-REJECT-{tags.get(34, 'UNKNOWN')}"),
            timestamp=_timestamp(tags.get(52)),
            symbol=symbol,
            side=side,
            event_type=EventType.ORDER_CANCEL_REJECTED,
            last_qty=None,
            last_px=None,
            order_id=order_id,
            cl_ord_id=cl_ord_id,
            order_status=OrderStatus.CANCEL_REJECTED,
            source=source,
        )
    if message_type != "8":
        return None

    exec_type = tags.get(FixTag.EXEC_TYPE)
    status = tags.get(FixTag.ORDER_STATUS)
    if exec_type == "8" or status == "8":
        event_type, order_status = EventType.ORDER_REJECTED, OrderStatus.REJECTED
    elif exec_type == "4" or status == "4":
        event_type, order_status = EventType.ORDER_CANCELED, OrderStatus.CANCELED
    elif tags.get(FixTag.LAST_QTY) and tags.get(FixTag.LAST_PX):
        event_type = EventType.TRADE
        order_status = (
            OrderStatus.FILLED if status == "2" else OrderStatus.PARTIALLY_FILLED
        )
    elif status == "2":
        event_type, order_status = EventType.ORDER_FILLED, OrderStatus.FILLED
    elif status == "1":
        event_type, order_status = EventType.ORDER_PARTIALLY_FILLED, OrderStatus.PARTIALLY_FILLED
    else:
        event_type, order_status = EventType.STATUS, None

    def integer(tag: FixTag) -> int | None:
        value = tags.get(tag)
        return int(value) if value is not None else None

    def decimal(tag: FixTag) -> Decimal | None:
        value = tags.get(tag)
        return Decimal(value) if value is not None else None

    exec_id = tags.get(FixTag.EXEC_ID)
    return TradingEvent(
        event_id=exec_id or f"STATUS-{tags.get(34, 'UNKNOWN')}",
        timestamp=_timestamp(tags.get(52)),
        symbol=symbol,
        side=side,
        event_type=event_type,
        last_qty=integer(FixTag.LAST_QTY),
        last_px=decimal(FixTag.LAST_PX),
        order_id=order_id,
        cl_ord_id=cl_ord_id,
        exec_id=exec_id,
        cum_qty=integer(FixTag.CUM_QTY),
        leaves_qty=integer(FixTag.LEAVES_QTY),
        order_status=order_status,
        source=source,
    )


class TradingDataService:
    """Coordinates normalization, correlation, persistence, and snapshots."""

    def __init__(self, database: str = ":memory:", *, event_observer=None) -> None:
        self.event_observer = event_observer
        self.repository = SQLiteTradingRepository(database)
        self.correlator = OrderCorrelator()
        self.processed = 0
        self.parse_errors = 0
        self.unmatched = 0
        self.recent_events: list[dict[str, Any]] = []

    def close(self) -> None:
        self.repository.close()

    def ingest(self, message: SyntheticMessage) -> dict[str, Any]:
        self.processed += 1
        parsed = split_message(message.raw_message)
        errors = parsed.errors
        accepted = not errors
        self.repository.save_message(
            run_id=None,
            sequence=message.sequence,
            raw_message=message.raw_message,
            message_type=parsed.message_type,
            accepted=accepted,
            parse_error="; ".join(error.code for error in errors) or None,
            received_at=message.timestamp.isoformat(),
        )
        if errors:
            self.parse_errors += 1
            return self.snapshot()
        preflight = getattr(self.event_observer, "accept_message", None)
        if preflight is not None and not preflight(parsed, message.raw_message):
            return self.snapshot()
        event = normalize_fix_message(message.raw_message)
        if event is None:
            return self.snapshot()
        tags = _tags(parsed)
        result = self.correlator.apply(
            event,
            order_qty=int(tags[FixTag.ORDER_QTY]) if event.event_type is EventType.ORDER_NEW else None,
        )
        if self.event_observer is not None:
            self.event_observer(event, result, parsed, message.raw_message)
        if not result.accepted:
            if result.reason == "UNMATCHED_ORDER":
                self.unmatched += 1
        elif event.event_type is EventType.ORDER_NEW:
            self.repository.upsert_order(event, int(tags[FixTag.ORDER_QTY]))
        elif event.exec_id is not None:
            self.repository.save_execution(event, tags.get(FixTag.EXEC_TYPE))
        if result.accepted and not result.duplicate:
            self.recent_events = [event.to_dict(), *self.recent_events[:19]]
        return self.snapshot()

    def snapshot(self) -> dict[str, Any]:
        buy = 0
        sell = 0
        rankings: dict[str, dict[str, float]] = {}
        for order in self.correlator.orders_by_cl_ord_id.values():
            row = rankings.setdefault(order.symbol, {"buy_volume": 0, "sell_volume": 0, "volume": 0})
            row["volume"] += order.cum_qty
            row["buy_volume" if order.side == "BUY" else "sell_volume"] += order.cum_qty
            buy += order.cum_qty if order.side == "BUY" else 0
            sell += order.cum_qty if order.side == "SELL" else 0
        ranking_rows = [{"symbol": symbol, **values} for symbol, values in rankings.items()]
        ranking_rows.sort(key=lambda row: row["volume"], reverse=True)
        return {
            "processed": self.processed,
            "orders": len(self.correlator.orders_by_cl_ord_id),
            "executions": len(self.correlator.seen_exec_ids),
            "duplicates": len(self.correlator.duplicate_exec_ids),
            "parse_errors": self.parse_errors,
            "unmatched_events": self.unmatched,
            "flow": {"buy_volume": buy, "sell_volume": sell},
            "rankings": ranking_rows,
            "recent_events": self.recent_events,
        }
