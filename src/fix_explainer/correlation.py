"""Order correlation, execution de-duplication, and status transitions."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from .events import EventType, OrderStatus, TradingEvent


@dataclass
class CorrelatedOrder:
    cl_ord_id: str
    order_id: str | None
    symbol: str
    side: str
    order_qty: int
    cum_qty: int = 0
    leaves_qty: int = 0
    status: OrderStatus = OrderStatus.NEW
    notional: Decimal = Decimal("0")


@dataclass(frozen=True)
class CorrelationResult:
    """Outcome of applying one normalized event."""

    accepted: bool
    duplicate: bool
    order: CorrelatedOrder | None
    reason: str | None = None


@dataclass
class OrderCorrelator:
    """Maintain order state while making execution application idempotent."""

    orders_by_cl_ord_id: dict[str, CorrelatedOrder] = field(default_factory=dict)
    cl_ord_id_by_order_id: dict[str, str] = field(default_factory=dict)
    seen_exec_ids: set[str] = field(default_factory=set)
    duplicate_exec_ids: set[str] = field(default_factory=set)
    errors: list[str] = field(default_factory=list)

    def apply(self, event: TradingEvent, order_qty: int | None = None) -> CorrelationResult:
        """Apply an event, returning an explicit result instead of hiding errors."""
        if event.event_type is EventType.ORDER_NEW:
            return self._new_order(event, order_qty)

        order = self._find_order(event)
        if order is None:
            return self._reject("UNMATCHED_ORDER", event)

        if event.exec_id is not None:
            if event.exec_id in self.seen_exec_ids:
                self.duplicate_exec_ids.add(event.exec_id)
                return CorrelationResult(True, True, order, "DUPLICATE_EXECUTION")
            self.seen_exec_ids.add(event.exec_id)

        if event.event_type is EventType.TRADE:
            return self._apply_trade(order, event)
        if event.event_type is EventType.ORDER_PARTIALLY_FILLED:
            return self._transition(order, OrderStatus.PARTIALLY_FILLED, event)
        if event.event_type is EventType.ORDER_FILLED:
            return self._transition(order, OrderStatus.FILLED, event)
        if event.event_type is EventType.ORDER_CANCELED:
            return self._transition(order, OrderStatus.CANCELED, event)
        if event.event_type is EventType.ORDER_REJECTED:
            return self._transition(order, OrderStatus.REJECTED, event)
        if event.event_type is EventType.ORDER_CANCEL_REJECTED:
            return self._transition(order, OrderStatus.CANCEL_REJECTED, event)
        return CorrelationResult(True, False, order)

    def _new_order(
        self, event: TradingEvent, order_qty: int | None
    ) -> CorrelationResult:
        if event.cl_ord_id is None:
            return self._reject("MISSING_CL_ORD_ID", event)
        if order_qty is None or order_qty <= 0:
            return self._reject("INVALID_ORDER_QTY", event)
        if event.cl_ord_id in self.orders_by_cl_ord_id:
            return self._reject("DUPLICATE_ORDER", event)
        if event.order_id is not None and event.order_id in self.cl_ord_id_by_order_id:
            return self._reject("DUPLICATE_ORDER_ID", event)
        order = CorrelatedOrder(
            cl_ord_id=event.cl_ord_id,
            order_id=event.order_id,
            symbol=event.symbol,
            side=event.side.value,
            order_qty=order_qty,
            leaves_qty=order_qty,
        )
        self.orders_by_cl_ord_id[event.cl_ord_id] = order
        if event.order_id is not None:
            self.cl_ord_id_by_order_id[event.order_id] = event.cl_ord_id
        return CorrelationResult(True, False, order)

    def _apply_trade(
        self, order: CorrelatedOrder, event: TradingEvent
    ) -> CorrelationResult:
        quantity = event.last_qty or 0
        if quantity <= 0 or event.last_px is None:
            return self._reject("INVALID_TRADE_QUANTITY_OR_PRICE", event, order)
        if order.status in {OrderStatus.FILLED, OrderStatus.CANCELED, OrderStatus.REJECTED}:
            return self._reject("INVALID_TERMINAL_STATE_TRANSITION", event, order)
        if order.cum_qty + quantity > order.order_qty:
            return self._reject("OVERFILL", event, order)
        order.cum_qty += quantity
        order.leaves_qty = order.order_qty - order.cum_qty
        order.notional += Decimal(quantity) * event.last_px
        order.status = (
            OrderStatus.FILLED
            if order.leaves_qty == 0
            else OrderStatus.PARTIALLY_FILLED
        )
        return CorrelationResult(True, False, order)

    def _transition(
        self,
        order: CorrelatedOrder,
        target: OrderStatus,
        event: TradingEvent,
    ) -> CorrelationResult:
        allowed = {
            OrderStatus.NEW: {
                OrderStatus.PARTIALLY_FILLED,
                OrderStatus.FILLED,
                OrderStatus.CANCELED,
                OrderStatus.REJECTED,
                OrderStatus.CANCEL_REJECTED,
            },
            OrderStatus.PARTIALLY_FILLED: {
                OrderStatus.PARTIALLY_FILLED,
                OrderStatus.FILLED,
                OrderStatus.CANCELED,
            },
            OrderStatus.CANCEL_REJECTED: {OrderStatus.CANCEL_REJECTED},
        }
        if target not in allowed.get(order.status, set()):
            return self._reject("INVALID_STATUS_TRANSITION", event, order)
        order.status = target
        if target is OrderStatus.FILLED:
            order.leaves_qty = 0
        return CorrelationResult(True, False, order)

    def _find_order(self, event: TradingEvent) -> CorrelatedOrder | None:
        if event.cl_ord_id is not None:
            order = self.orders_by_cl_ord_id.get(event.cl_ord_id)
            if order is not None:
                return order
        if event.order_id is not None:
            cl_ord_id = self.cl_ord_id_by_order_id.get(event.order_id)
            if cl_ord_id is not None:
                return self.orders_by_cl_ord_id[cl_ord_id]
        return None

    def _reject(
        self,
        reason: str,
        event: TradingEvent,
        order: CorrelatedOrder | None = None,
    ) -> CorrelationResult:
        detail = f"{reason}:{event.event_id}"
        self.errors.append(detail)
        return CorrelationResult(False, False, order, reason)
