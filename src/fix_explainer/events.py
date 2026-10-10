"""Shared contract for validated FIX trading events.

This module is the boundary between FIX-specific processing and consumers such
as the dashboard or bounded AI explanation provider.  Raw FIX messages are
kept outside this contract; only validated domain events should be emitted.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from enum import StrEnum, IntEnum
from typing import Any


class FixTag(IntEnum):
    """FIX tags used by the trading-flow normalizer."""

    CL_ORD_ID = 11
    ORDER_ID = 37
    EXEC_ID = 17
    SYMBOL = 55
    SIDE = 54
    ORDER_QTY = 38
    LAST_QTY = 32
    LAST_PX = 31
    CUM_QTY = 14
    LEAVES_QTY = 151
    PRICE = 44
    ORDER_TYPE = 40
    TIME_IN_FORCE = 59
    ORDER_STATUS = 39
    EXEC_TYPE = 150
    MESSAGE_TYPE = 35


class EventType(StrEnum):
    """Consumer-facing event categories."""

    ORDER_NEW = "ORDER_NEW"
    TRADE = "TRADE"
    ORDER_PARTIALLY_FILLED = "ORDER_PARTIALLY_FILLED"
    ORDER_FILLED = "ORDER_FILLED"
    ORDER_CANCELED = "ORDER_CANCELED"
    ORDER_REJECTED = "ORDER_REJECTED"
    ORDER_CANCEL_REJECTED = "ORDER_CANCEL_REJECTED"
    STATUS = "STATUS"
    CORRECTION = "CORRECTION"
    REJECTED_EVENT = "REJECTED_EVENT"


class Side(StrEnum):
    BUY = "BUY"
    SELL = "SELL"


class OrderStatus(StrEnum):
    NEW = "NEW"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED = "FILLED"
    CANCELED = "CANCELED"
    REJECTED = "REJECTED"
    CANCEL_REJECTED = "CANCEL_REJECTED"


class EventSource(StrEnum):
    SIMULATED = "SIMULATED"
    LIVE = "LIVE"


def _utc_timestamp(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timestamp must be timezone-aware")
    return value.astimezone(timezone.utc).isoformat(timespec="milliseconds").replace(
        "+00:00", "Z"
    )


@dataclass(frozen=True, slots=True)
class TradingEvent:
    """A validated event emitted for downstream trading-flow consumers.

    ``TRADE`` is reserved for a confirmed execution with positive quantity and
    price.  Other event types may carry zero or null execution fields.
    """

    event_id: str
    timestamp: datetime
    symbol: str
    side: Side
    event_type: EventType
    last_qty: int | None
    last_px: Decimal | None
    order_id: str | None
    source: EventSource
    cl_ord_id: str | None = None
    exec_id: str | None = None
    cum_qty: int | None = None
    leaves_qty: int | None = None
    order_status: OrderStatus | None = None

    def __post_init__(self) -> None:
        if not self.event_id.strip():
            raise ValueError("event_id must not be empty")
        if not self.symbol.strip():
            raise ValueError("symbol must not be empty")
        if self.last_qty is not None and self.last_qty < 0:
            raise ValueError("last_qty must be non-negative")
        if self.cum_qty is not None and self.cum_qty < 0:
            raise ValueError("cum_qty must be non-negative")
        if self.leaves_qty is not None and self.leaves_qty < 0:
            raise ValueError("leaves_qty must be non-negative")
        if self.last_px is not None and self.last_px < 0:
            raise ValueError("last_px must be non-negative")
        if self.event_type is EventType.TRADE and (
            self.last_qty is None
            or self.last_qty <= 0
            or self.last_px is None
        ):
            raise ValueError("TRADE requires positive last_qty and last_px")

    def to_dict(self) -> dict[str, Any]:
        """Return the stable JSON-shaped contract shared by all consumers."""
        return {
            "event_id": self.event_id,
            "timestamp": _utc_timestamp(self.timestamp),
            "symbol": self.symbol,
            "side": self.side.value,
            "event_type": self.event_type.value,
            "last_qty": self.last_qty,
            "last_px": float(self.last_px) if self.last_px is not None else None,
            "order_id": self.order_id,
            "cl_ord_id": self.cl_ord_id,
            "exec_id": self.exec_id,
            "cum_qty": self.cum_qty,
            "leaves_qty": self.leaves_qty,
            "order_status": (
                self.order_status.value if self.order_status is not None else None
            ),
            "source": self.source.value,
        }
