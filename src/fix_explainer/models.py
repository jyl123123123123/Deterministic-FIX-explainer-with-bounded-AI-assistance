"""Core immutable data structures shared by FIX parsing and validation."""

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class FixField:
    """A single FIX tag-value field with its source position preserved."""

    tag: int
    value: str
    raw_value: bytes
    ordinal: int
    start_offset: int
    end_offset: int


@dataclass(frozen=True)
class ValidationError:
    """A deterministic validation finding tied to a field when possible."""

    code: str
    message: str
    severity: Literal["error", "warning"]
    tag: int | None = None
    ordinal: int | None = None