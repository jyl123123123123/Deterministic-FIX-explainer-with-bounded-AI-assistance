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
]
from .template import TemplateExplanationProvider

from .ai import GeminiExplanationProvider, build_ai_catalog
