"""Template by default; --mock tests integration; --ai calls Gemini explicitly."""
import sys

if sys.version_info < (3, 11):
    raise SystemExit("Python 3.11+ is required. Run this example with your Python 3.11+ virtual environment.")

import argparse
import json
from pathlib import Path
from fix_explainer import (
    GeminiExplanationProvider, TemplateExplanationProvider, split_message,
    load_orchestra, validate_integrity, validate_message_schema, explain_with_provider,
)


def mock_transport(model, key, payload, timeout):
    catalog = json.loads(payload['contents'][0]['parts'][0]['text'])
    return json.dumps({'items': [{'source_id': row['source_id'], 'variant': 1} for row in catalog]})


def main():
    parser = argparse.ArgumentParser()
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument('--ai', action='store_true', help='Call Gemini using environment configuration')
    modes.add_argument('--mock', action='store_true', help='Exercise AI pipeline without network/key')
    parser.add_argument('--file', type=Path, help='One FIX message with SOH or pipe delimiters')
    args = parser.parse_args()
    fixtures = Path(__file__).resolve().parents[1] / 'tests' / 'fixtures'
    payload = (args.file or fixtures / 'new_order_single.fix').read_bytes().rstrip(b'\r\n')
    # Readable fixtures use pipes; byte-accurate integrity uses normalized SOH payload.
    if b'\x01' not in payload:
        payload = payload.replace(b'|', b'\x01')
    message = split_message(payload)
    specification = load_orchestra(fixtures / 'fix_orchestra_subset.xml')
    errors = (*validate_integrity(payload, message), *validate_message_schema(message, specification))
    if args.ai:
        provider = GeminiExplanationProvider()
    elif args.mock:
        provider = GeminiExplanationProvider(model='gemini-mock', api_key='mock', transport=mock_transport)
    else:
        provider = TemplateExplanationProvider()
    result = explain_with_provider(message, provider, specification, errors)
    # Do not print original context or diagnostic text to console logs.
    print(result['provider_summary'])
    if result['fallback_used']:
        print('FALLBACK:', result['fallback_reason'])
    print('Validation findings:', len(result['deterministic']['validation_errors']))


if __name__ == '__main__':
    main()
