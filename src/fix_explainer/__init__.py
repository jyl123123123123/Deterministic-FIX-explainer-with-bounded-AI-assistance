"""Deterministic FIX message parsing and explanation package."""

from .models import FixField, ValidationError
from .message import ParsedFixMessage, split_message
from .integrity import validate_body_length, validate_checksum, validate_integrity
from .spec import FieldSpec, FixSpecification, MessageSpec, load_orchestra
from .schema import validate_message_schema
from .serialization import message_to_dict, message_to_json
from .explainer import (
	BoundedExplanationProvider,
	build_explanation_context,
	explain_deterministically,
	explain_with_provider,
)
from .tokenizer import TokenizationResult, tokenize
from .events import (
	EventSource,
	EventType,
	FixTag,
	OrderStatus,
	Side,
	TradingEvent,
)
from .synthetic import SyntheticMessage, generate_synthetic_messages
from .batch import BatchItem, BatchResult, parse_batch
from .storage import SQLiteTradingRepository
from .correlation import CorrelatedOrder, CorrelationResult, OrderCorrelator
from .streaming import StreamConfig, StreamRun, StreamSimulator
from .trading import TradingDataService, normalize_fix_message

__version__ = "0.1.0"

__all__ = [
	"GeminiExplanationProvider",
	"build_ai_catalog",
	"TemplateExplanationProvider",
	"FixField",
	"FieldSpec",
	"FixSpecification",
	"BoundedExplanationProvider",
	"MessageSpec",
	"ParsedFixMessage",
	"TokenizationResult",
	"ValidationError",
	"__version__",
	"split_message",
	"tokenize",
	"load_orchestra",
	"message_to_dict",
	"message_to_json",
	"build_explanation_context",
	"explain_deterministically",
	"explain_with_provider",
	"validate_body_length",
	"validate_checksum",
	"validate_integrity",
	"validate_message_schema",
	"EventSource",
	"EventType",
	"FixTag",
	"OrderStatus",
	"Side",
	"TradingEvent",
	"SyntheticMessage",
	"generate_synthetic_messages",
	"BatchItem",
	"BatchResult",
	"parse_batch",
	"SQLiteTradingRepository",
	"CorrelatedOrder",
	"CorrelationResult",
	"OrderCorrelator",
	"StreamConfig",
	"StreamRun",
	"StreamSimulator",
	"TradingDataService",
	"normalize_fix_message",
]
from .template import TemplateExplanationProvider

from .ai import GeminiExplanationProvider, build_ai_catalog
