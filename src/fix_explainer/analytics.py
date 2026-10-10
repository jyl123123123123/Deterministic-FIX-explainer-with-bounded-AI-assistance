"""Deterministic, event-time analytics for an observed FIX flow.

Only validated new orders and new fills enter this ledger. Monetary values are
Decimal strings; currencies are never combined. This is an in-memory demo ledger.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal, localcontext
from hashlib import sha256
import json
import re
from threading import RLock


@dataclass(frozen=True)
class AnalyticsEvent:
    session_id: str
    event_id: str
    timestamp: datetime
    symbol: str
    side: str
    kind: str
    quantity: int
    price: Decimal | None = None
    currency: str = 'UNSPECIFIED'
    source: str = 'SIMULATED'


class TradingAnalytics:
    def __init__(self, capacity=10000):
        self.capacity = capacity
        self._events = {}
        self._lock = RLock()
        self.findings = Counter()

    def reject(self, code):
        with self._lock:
            self.findings[code] += 1

    def ingest(self, event: AnalyticsEvent):
        """Return accepted/duplicate; conflicting IDs fail without changing totals."""
        with self._lock:
            if (not event.session_id or not event.event_id or
                event.timestamp.tzinfo is None or event.timestamp.utcoffset() is None or
                event.kind not in ('ORDER_NEW', 'TRADE') or event.side not in ('BUY', 'SELL') or
                not re.fullmatch(r'[A-Za-z0-9._-]{1,32}', event.symbol) or
                not re.fullmatch(r'[A-Z]{3}|UNSPECIFIED', event.currency) or
                event.source not in ('SIMULATED', 'LIVE') or
                type(event.quantity) is not int or not 0 < event.quantity <= 10**12):
                raise ValueError('Invalid analytics event')
            if event.kind == 'TRADE' and (
                not isinstance(event.price, Decimal) or not event.price.is_finite() or
                not 0 < event.price <= Decimal('1e12') or event.price.as_tuple().exponent < -12):
                raise ValueError('Invalid fill price')
            if event.kind == 'ORDER_NEW' and event.price is not None:
                raise ValueError('Order demand does not imply executed notional')
            key = (event.session_id, event.kind, event.event_id)
            previous = self._events.get(key)
            if previous is not None:
                if previous != event:
                    self.findings['CONFLICTING_EVENT_ID'] += 1
                    raise ValueError('Conflicting event ID')
                return 'duplicate'
            if len(self._events) >= self.capacity:
                self.findings['CAPACITY_REACHED'] += 1
                raise ValueError('Analytics capacity reached')
            self._events[key] = event
            return 'accepted'

    @staticmethod
    def _aggregate(events):
        rows = {}
        with localcontext() as ctx:
            ctx.prec = 80
            for event in events:
                key = (event.symbol, event.currency)
                row = rows.setdefault(key, dict(symbol=event.symbol, currency=event.currency,
                    buy_order_qty=0, sell_order_qty=0, orders=0, executions=0,
                    buy_fill_qty=0, sell_fill_qty=0, buy_notional=Decimal(0), sell_notional=Decimal(0)))
                side = event.side.lower()
                if event.kind == 'ORDER_NEW':
                    row['orders'] += 1
                    row[side + '_order_qty'] += event.quantity
                else:
                    row['executions'] += 1
                    row[side + '_fill_qty'] += event.quantity
                    row[side + '_notional'] += event.quantity * event.price
            for row in rows.values():
                row['gross_notional'] = row['buy_notional'] + row['sell_notional']
                row['observed_side_notional_difference'] = row['buy_notional'] - row['sell_notional']
                for name, value in list(row.items()):
                    if isinstance(value, Decimal):
                        row[name] = format(value.normalize(), 'f')
        # No cross-currency monetary ranking.
        return [rows[key] for key in sorted(rows)]

    def snapshot(self, window_seconds=300, as_of=None):
        if type(window_seconds) is not int or not 1 <= window_seconds <= 86400:
            raise ValueError('Window must be 1 to 86400 seconds')
        with self._lock:
            events = tuple(self._events.values())
            findings = dict(sorted(self.findings.items()))
        end = as_of or max((e.timestamp for e in events), default=datetime(1970, 1, 1, tzinfo=timezone.utc))
        if end.tzinfo is None or end.utcoffset() is None:
            raise ValueError('as_of must include a timezone')
        end = end.astimezone(timezone.utc)
        start = end - timedelta(seconds=window_seconds)
        previous_start = start - timedelta(seconds=window_seconds)
        current_events = [e for e in events if start < e.timestamp <= end]
        rows = self._aggregate(current_events)
        previous = self._aggregate(e for e in events if previous_start < e.timestamp <= start)
        baseline = {(r['symbol'], r['currency']): (i, r) for i, r in enumerate(previous)}
        anomalies = []
        for i, row in enumerate(rows):
            j, before = baseline.get((row['symbol'], row['currency']), (None, {}))
            for side in ('buy', 'sell'):
                metric = side + '_fill_qty'
                old, new = before.get(metric, 0), row[metric]
                if old > 0 and new >= 2 * old and new - old >= 100:
                    anomalies.append(dict(code='REPORTED_FILL_QTY_INCREASE', symbol=row['symbol'],
                        currency=row['currency'], side=side.upper(), previous=old, current=new,
                        evidence=[f'/symbols/{i}/{metric}', f'/previous_symbols/{j}/{metric}']))
        currency_totals = []
        with localcontext() as ctx:
            ctx.prec = 80
            for currency in sorted({r['currency'] for r in rows}):
                group = [r for r in rows if r['currency'] == currency]
                currency_totals.append(dict(currency=currency,
                    gross_notional=format(sum((Decimal(r['gross_notional']) for r in group), Decimal(0)).normalize(), 'f'),
                    executions=sum(r['executions'] for r in group)))
        report = dict(currency_totals=currency_totals, window_seconds=window_seconds, window_start=start.isoformat(),
            window_end=end.isoformat(), interval='(start, end]', previous_window_start=previous_start.isoformat(),
            data_scope='connected_fix_sessions', sources=sorted({e.source for e in current_events}),
            total_executions=sum(r['executions'] for r in rows),
            total_orders=sum(r['orders'] for r in rows), symbols=rows, previous_symbols=previous,
            anomalies=anomalies, findings=findings,
            limitations=['Observed sides are not aggressor sides or market-wide capital flow.',
                'UNSPECIFIED currency has no implied USD denomination.',
                'Corrections and trade cancellations are unsupported and excluded.',
                'In-memory ledger; restart clears history.'])
        encoded = json.dumps(report, sort_keys=True, separators=(',', ':')).encode()
        return {'snapshot_id': sha256(encoded).hexdigest(), **report}
