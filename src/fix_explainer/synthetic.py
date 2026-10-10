"""Reproducible synthetic FIX messages for stream and parser development."""

from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class SyntheticMessage:
    """One ordered raw FIX message and its generation metadata."""

    sequence: int
    timestamp: datetime
    raw_message: bytes
    message_type: str
    scenario: str
    cl_ord_id: str
    order_id: str
    exec_id: str | None
    is_duplicate: bool = False


SYMBOLS = ("AAPL", "MSFT", "NVDA", "AMZN", "TSLA", "META", "GOOGL", "AMD")
SCENARIOS = (
    "FULL_FILL",
    "PARTIAL_FILL",
    "CANCEL",
    "REJECT",
    "CANCEL_REJECT",
    "FULL_FILL",
    "PARTIAL_FILL",
    "STATUS",
)


def generate_synthetic_messages(
    count: int = 1500,
    seed: int = 20261010,
    start_time: datetime | None = None,
) -> list[SyntheticMessage]:
    """Generate ``count`` time-ordered messages for deterministic testing.

    The generator creates complete order lifecycles where possible and trims
    only the final lifecycle to honor the requested exact message count.
    """
    if not 1000 <= count <= 2000:
        raise ValueError("count must be between 1000 and 2000")
    if start_time is None:
        start_time = datetime(2026, 10, 10, 17, 0, tzinfo=timezone.utc)
    if start_time.tzinfo is None or start_time.utcoffset() is None:
        raise ValueError("start_time must be timezone-aware")

    rng = random.Random(seed)
    messages: list[SyntheticMessage] = []
    order_number = 0
    while len(messages) < count:
        order_number += 1
        scenario = SCENARIOS[(order_number - 1) % len(SCENARIOS)]
        symbol = rng.choice(SYMBOLS)
        side = "1" if order_number % 2 else "2"
        quantity = rng.choice((100, 200, 500, 1000))
        price = Decimal(str(rng.choice((85, 120, 185.5, 240, 415.25))))
        cl_ord_id = f"SIM-{order_number:05d}"
        order_id = f"ORD-{order_number:05d}"
        order_time = start_time + timedelta(milliseconds=order_number * 100)
        lifecycle = _lifecycle(
            scenario,
            cl_ord_id,
            order_id,
            symbol,
            side,
            quantity,
            price,
            order_time,
            rng,
        )
        messages.extend(lifecycle)

    return [
        SyntheticMessage(
            sequence=index + 1,
            timestamp=message.timestamp,
            raw_message=message.raw_message,
            message_type=message.message_type,
            scenario=message.scenario,
            cl_ord_id=message.cl_ord_id,
            order_id=message.order_id,
            exec_id=message.exec_id,
            is_duplicate=message.is_duplicate,
        )
        for index, message in enumerate(messages[:count])
    ]


def _lifecycle(
    scenario: str,
    cl_ord_id: str,
    order_id: str,
    symbol: str,
    side: str,
    quantity: int,
    price: Decimal,
    timestamp: datetime,
    rng: random.Random,
) -> list[SyntheticMessage]:
    messages = [
        _message(
            "D",
            scenario,
            cl_ord_id,
            order_id,
            None,
            timestamp,
            [
                (11, cl_ord_id),
                (55, symbol),
                (54, side),
                (38, str(quantity)),
                (40, "2"),
                (44, f"{price:.2f}"),
                (59, "0"),
            ],
        )
    ]
    if scenario == "REJECT":
        return messages + [
            _message("8", scenario, cl_ord_id, order_id, f"EXEC-{cl_ord_id}", timestamp, [
                (150, "8"), (39, "8"), (58, "Risk limit exceeded"),
            ])
        ]
    if scenario == "CANCEL_REJECT":
        return messages + [
            _message("F", scenario, cl_ord_id, order_id, None, timestamp, [(41, cl_ord_id)]),
            _message("9", scenario, cl_ord_id, order_id, f"EXEC-{cl_ord_id}", timestamp, [
                (434, "1"), (102, "0"), (58, "Order already closed"),
            ]),
        ]
    if scenario == "CANCEL":
        return messages + [
            _message("F", scenario, cl_ord_id, order_id, None, timestamp, [(41, cl_ord_id)]),
            _message("8", scenario, cl_ord_id, order_id, f"EXEC-{cl_ord_id}", timestamp, [
                (150, "4"), (39, "4"), (14, "0"), (151, str(quantity)),
            ]),
        ]
    if scenario == "STATUS":
        return messages + [
            _message("8", scenario, cl_ord_id, order_id, f"EXEC-{cl_ord_id}", timestamp, [
                (150, "A"), (39, "0"), (14, "0"), (151, str(quantity)),
            ])
        ]

    first_fill = quantity if scenario == "FULL_FILL" else max(1, quantity // 2)
    messages.append(
        _message("8", scenario, cl_ord_id, order_id, f"EXEC-{cl_ord_id}-1", timestamp, [
            (150, "F"), (39, "1" if first_fill < quantity else "2"),
            (32, str(first_fill)), (31, f"{price:.2f}"),
            (14, str(first_fill)), (151, str(quantity - first_fill)),
        ])
    )
    if first_fill < quantity:
        messages.append(
            _message("8", scenario, cl_ord_id, order_id, f"EXEC-{cl_ord_id}-2", timestamp, [
                (150, "F"), (39, "2"), (32, str(quantity - first_fill)),
                (31, f"{price:.2f}"), (14, str(quantity)), (151, "0"),
            ])
        )
    if rng.random() < 0.08:
        messages.append(
            _message(
                "8",
                scenario,
                cl_ord_id,
                order_id,
                f"EXEC-{cl_ord_id}-1",
                timestamp,
                [(150, "F"), (39, "1"), (32, str(first_fill)), (31, f"{price:.2f}")],
                is_duplicate=True,
            )
        )
    return messages


def _message(
    message_type: str,
    scenario: str,
    cl_ord_id: str,
    order_id: str,
    exec_id: str | None,
    timestamp: datetime,
    body_fields: list[tuple[int, str]],
    is_duplicate: bool = False,
) -> SyntheticMessage:
    fields = [
        (35, message_type),
        (34, cl_ord_id.removeprefix("SIM-")),
        (49, "SIM_CLIENT"),
        (56, "SIM_EXCHANGE"),
        (52, timestamp.strftime("%Y%m%d-%H:%M:%S")),
        (37, order_id),
        *body_fields,
    ]
    if exec_id is not None and not any(tag == 17 for tag, _ in fields):
        fields.insert(6, (17, exec_id))
    raw = _encode_fix(fields)
    return SyntheticMessage(
        sequence=0,
        timestamp=timestamp,
        raw_message=raw,
        message_type=message_type,
        scenario=scenario,
        cl_ord_id=cl_ord_id,
        order_id=order_id,
        exec_id=exec_id,
        is_duplicate=is_duplicate,
    )


def _encode_fix(fields: list[tuple[int, str]]) -> bytes:
    delimiter = b"\x01"
    body = delimiter.join(f"{tag}={value}".encode("ascii") for tag, value in fields) + delimiter
    prefix = b"8=FIX.4.4\x019=" + str(len(body)).zfill(3).encode("ascii") + delimiter
    without_checksum = prefix + body
    checksum = sum(without_checksum) % 256
    return without_checksum + f"10={checksum:03d}".encode("ascii") + delimiter
