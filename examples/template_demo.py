"""Run from repository root: PYTHONPATH=src python3 examples/template_demo.py"""
import sys

if sys.version_info < (3, 11):
    raise SystemExit("Python 3.11+ is required. Run this example with your Python 3.11+ virtual environment.")

import json
from pathlib import Path
from fix_explainer import (
    TemplateExplanationProvider, split_message, load_orchestra,
    validate_integrity, validate_message_schema, explain_with_provider,
)

root = Path(__file__).resolve().parents[1]
fixtures = root / 'tests' / 'fixtures'
payload = (fixtures / 'new_order_single.fix').read_bytes().rstrip(b'\r\n').replace(b'|', b'\x01')
message = split_message(payload)
spec = load_orchestra(fixtures / 'fix_orchestra_subset.xml')
errors = (*validate_integrity(payload, message), *validate_message_schema(message, spec))
result = explain_with_provider(message, TemplateExplanationProvider(), spec, errors)
print(json.dumps(result, indent=2))
