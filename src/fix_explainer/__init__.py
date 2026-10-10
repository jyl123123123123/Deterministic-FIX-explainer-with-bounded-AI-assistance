"""Deterministic FIX message parsing and explanation package."""

from .models import FixField, ValidationError

__version__ = "0.1.0"

__all__ = ["FixField", "ValidationError", "__version__"]