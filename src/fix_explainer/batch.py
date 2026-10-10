"""Bounded batch processing built on the existing single-message decoder."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from .integrity import validate_integrity
from .message import ParsedFixMessage, split_message
from .models import ValidationError

MAX_BATCH_SIZE = 2000


@dataclass(frozen=True, slots=True)
class BatchItem:
    """One independently processed message in a batch."""

    sequence: int
    raw_message: bytes
    parsed: ParsedFixMessage
    errors: tuple[ValidationError, ...]

    @property
    def accepted(self) -> bool:
        return not any(error.severity == "error" for error in self.errors)


@dataclass(frozen=True, slots=True)
class BatchResult:
    """Deterministic result containing successes and per-message findings."""

    items: tuple[BatchItem, ...]

    @property
    def accepted(self) -> int:
        return sum(item.accepted for item in self.items)

    @property
    def rejected(self) -> int:
        return len(self.items) - self.accepted

    @property
    def errors(self) -> tuple[ValidationError, ...]:
        return tuple(error for item in self.items for error in item.errors)


def parse_batch(
    messages: Iterable[bytes],
    *,
    delimiter: bytes = b"\x01",
    max_batch_size: int = MAX_BATCH_SIZE,
) -> BatchResult:
    """Parse a bounded batch without letting one bad message stop the batch.

    ``messages`` must contain complete FIX payloads.  Message boundaries are
    intentionally owned by the caller so a malformed message cannot consume
    the next message in the batch.
    """
    if not 1 <= max_batch_size <= MAX_BATCH_SIZE:
        raise ValueError(f"max_batch_size must be between 1 and {MAX_BATCH_SIZE}")
    if len(delimiter) != 1:
        raise ValueError("delimiter must be exactly one byte")

    items: list[BatchItem] = []
    iterator = iter(messages)
    for sequence in range(1, max_batch_size + 1):
        try:
            raw_message = next(iterator)
        except StopIteration:
            break
        if not isinstance(raw_message, bytes):
            raise TypeError("batch messages must be bytes")
        parsed = split_message(raw_message, delimiter=delimiter)
        errors = (*parsed.errors, *validate_integrity(raw_message, parsed, delimiter))
        items.append(
            BatchItem(
                sequence=sequence,
                raw_message=raw_message,
                parsed=parsed,
                errors=errors,
            )
        )
    else:
        try:
            next(iterator)
        except StopIteration:
            pass
        else:
            raise ValueError(f"batch cannot contain more than {max_batch_size} messages")

    return BatchResult(tuple(items))
