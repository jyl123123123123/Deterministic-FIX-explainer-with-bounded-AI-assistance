"""Consume A's correlated events without replacing its FIX parser."""
from datetime import datetime, timezone
import re

from .analytics import AnalyticsEvent
from .integrity import validate_integrity


class AnalyticsBridge:
    def __init__(self, analytics):
        self.analytics = analytics

    def accept_message(self, parsed, payload):
        """Reject unsupported wire events before they can change correlation state."""
        tags = {f.tag: f.value for f in parsed.fields}
        valid = (not parsed.errors and not validate_integrity(payload, parsed)
                 and len(tags) == len(parsed.fields) and tags.get(8) == 'FIX.4.4')
        if tags.get(35) == '8' and tags.get(150) in ('G', 'H'):
            valid = False
        if tags.get(35) == '8' and (32 in tags or 31 in tags) and tags.get(150) != 'F':
            valid = False
        try:
            datetime.strptime(tags[52], '%Y%m%d-%H:%M:%S')
            valid = valid and bool(tags.get(49)) and bool(tags.get(56))
            if 15 in tags:
                valid = valid and bool(re.fullmatch(r'[A-Z]{3}', tags[15]))
            if tags.get(35) == 'D':
                valid = valid and tags.get(54) in ('1', '2') and bool(re.fullmatch(r'[A-Za-z0-9._-]{1,32}', tags.get(55, ''))) and 0 < int(tags[38]) <= 10**12
            if tags.get(35) == '8' and tags.get(150) == 'F':
                from decimal import Decimal
                price = Decimal(tags[31])
                valid = valid and int(tags[32]) > 0 and price.is_finite() and 0 < price <= Decimal('1e12') and price.as_tuple().exponent >= -12 and bool(tags.get(17)) and tags.get(39) in ('1', '2')
        except (KeyError, ValueError, ArithmeticError):
            valid = False
        # A currently treats CancelRequest as canceled. Do not let a request
        # invalidate subsequent confirmed fills in the integrated B pipeline.
        if tags.get(35) == 'F':
            return False
        if not valid:
            self.analytics.reject('EXCLUDED_WIRE_OR_EXECUTION_TYPE')
        return valid

    def accept_event(self, event, correlator, parsed):
        """Check explicit metadata before A can mutate the matched order."""
        order = correlator._find_order(event)
        if order is None:
            return True  # A reports unmatched orders through its existing result.
        tags = {f.tag: f.value for f in parsed.fields}
        valid = ((55 not in tags or tags[55] == order.symbol) and
                 (54 not in tags or tags[54] == ('1' if order.side == 'BUY' else '2')))
        if not valid:
            self.analytics.reject('CONFLICTING_ORDER_METADATA')
        return valid

    def __call__(self, event, result, parsed, payload):
        tags = {f.tag: f.value for f in parsed.fields}
        if event.event_type.value not in ('ORDER_NEW', 'TRADE'):
            return
        try:
            if parsed.errors or validate_integrity(payload, parsed):
                raise ValueError('INVALID_WIRE_MESSAGE')
            if len(tags) != len(parsed.fields):
                raise ValueError('AMBIGUOUS_DUPLICATE_TAG')
            if tags.get(8) != 'FIX.4.4':
                raise ValueError('UNSUPPORTED_FIX_VERSION')
            if event.event_type.value == 'TRADE' and (tags.get(150) != 'F' or tags.get(39) not in ('1', '2')):
                raise ValueError('UNSUPPORTED_EXECUTION_TYPE')
            if not result.accepted or result.order is None:
                # Identical order replays may be rejected by A. They cannot add demand.
                raise ValueError('CORRELATION_REJECTED')
            order = result.order
            if tags.get(54, '1' if order.side == 'BUY' else '2') not in ('1', '2'):
                raise ValueError('INVALID_SIDE')
            if (55 in tags and tags[55] != order.symbol) or (54 in tags and tags[54] != ('1' if order.side == 'BUY' else '2')):
                raise ValueError('CONFLICTING_ORDER_METADATA')
            stamp = datetime.strptime(tags[52], '%Y%m%d-%H:%M:%S').replace(tzinfo=timezone.utc)
            # Session identifiers stay local and never enter reports or AI catalogs.
            session = tags[49] + '\x00' + tags[56]
            self.analytics.ingest(AnalyticsEvent(session, event.event_id, stamp,
                order.symbol, order.side, event.event_type.value,
                order.order_qty if event.event_type.value == 'ORDER_NEW' else event.last_qty,
                event.last_px, tags.get(15, 'UNSPECIFIED'), event.source.value))
        except (ValueError, KeyError, TypeError):
            self.analytics.reject('EXCLUDED_EVENT')
