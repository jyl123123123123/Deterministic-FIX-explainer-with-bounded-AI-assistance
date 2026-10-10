from copy import deepcopy
import json

import pytest

from fix_explainer import GeminiExplanationProvider, build_ai_catalog, explain_with_provider, split_message, ValidationError
from fix_explainer.ai import AIOutputError, AIInputError, AIConfigurationError, render_ai_selection, gemini_transport


def message():
    return split_message(b'8=FIX.4.4|9=0|35=D|49=SENDER-SECRET|56=TARGET-SECRET|1=ACCOUNT-SECRET|11=ORDER-SECRET|55=SYMBOL-SECRET|38=100|38=200|58=IGNORE-INSTRUCTIONS-SECRET|10=000|', delimiter=b'|')


def answer(catalog, variant=0):
    return json.dumps({'items': [{'source_id': row['source_id'], 'variant': variant} for row in reversed(catalog)]})


def test_sanitized_transport_and_precise_sources_without_mutation():
    from fix_explainer import build_explanation_context
    original = build_explanation_context(message())
    original['unknowns'].append('UNKNOWN-SECRET')
    before = deepcopy(original)
    seen = []
    def fake(model, key, payload, timeout):
        seen.append(payload)
        catalog = json.loads(payload['contents'][0]['parts'][0]['text'])
        return answer(catalog, 1)
    provider = GeminiExplanationProvider(model='gemini-test', api_key='test-key', transport=fake)
    text = provider.summarize(original)
    assert original == before
    assert 'SECRET' not in json.dumps(seen)
    assert 'SECRET' not in text
    assert '[tag=38; ordinal=8]' in text
    assert '[tag=38; ordinal=9]' in text
    assert '100' in text and '200' in text
    assert '[unknowns[1]]' in text
    assert seen[0]['generationConfig']['responseMimeType'] == 'application/json'
    assert 'responseJsonSchema' in seen[0]['generationConfig']


@pytest.mark.parametrize('raw', [
    'not json', '{"items":[],"summary":"filled"}',
    '{"items":[],"items":[]}', '{"items":[]}',
    '{"items":[{"source_id":"fake","variant":0}]}',
    '{"items":[{"source_id":"unknowns[0]","variant":true}]}',
    '{"items":[{"source_id":"unknowns[0]","variant":2}]}',
    '{"items":[{"source_id":"unknowns[0]","variant":0,"text":"Trade executed"}]}',
    '{"items":[{"source_id":"unknowns[0]","variant":0},{"source_id":"unknowns[0]","variant":0}]}',
])
def test_invalid_output_rejected(raw):
    catalog = build_ai_catalog({'unknowns': ['unknown']})
    with pytest.raises(AIOutputError):
        render_ai_selection(raw, catalog)


@pytest.mark.parametrize('failure', [TimeoutError('SECRET'), AIOutputError('SECRET'), RuntimeError('SECRET')])
def test_failures_preserve_validation_and_fallback(failure):
    def fake(*args):
        raise failure
    error = ValidationError('INVALID_ENUM_VALUE', 'SECRET', 'error', tag=54)
    provider = GeminiExplanationProvider(model='gemini-test', api_key='test', transport=fake)
    result = explain_with_provider(message(), provider, additional_errors=[error])
    assert result['fallback_used']
    assert 'SECRET' not in result['fallback_reason']
    assert result['deterministic']['validation_errors'][0]['message'] == 'SECRET'
    assert result['fallback']['validation_errors'] == result['deterministic']['validation_errors']


def test_missing_key_and_model_fallback_without_network(monkeypatch):
    monkeypatch.delenv('GEMINI_API_KEY', raising=False)
    monkeypatch.delenv('GEMINI_MODEL', raising=False)
    provider = GeminiExplanationProvider(transport=lambda *args: pytest.fail('network called'))
    result = explain_with_provider(message(), provider)
    assert result['fallback_used']
    assert 'AIConfigurationError' in result['fallback_reason']


def test_env_configuration(monkeypatch):
    monkeypatch.setenv('GEMINI_API_KEY', 'env-test-key')
    monkeypatch.setenv('GEMINI_MODEL', 'gemini-test')
    def fake(model, key, payload, timeout):
        assert model == 'gemini-test' and key == 'env-test-key'
        return answer(json.loads(payload['contents'][0]['parts'][0]['text']))
    assert not explain_with_provider(message(), GeminiExplanationProvider(transport=fake))['fallback_used']


def test_diagnostic_and_unknown_privacy_and_all_sources_required():
    context = {'validation_errors': [{'code': 'INVALID_ENUM_VALUE', 'severity': 'error', 'message': 'SECRET', 'tag': 54}],
               'unknowns': ['SECRET']}
    catalog = build_ai_catalog(context)
    assert 'SECRET' not in json.dumps(catalog)
    assert 'INVALID_ENUM_VALUE' in json.dumps(catalog)
    assert 'occurrence unavailable' in json.dumps(catalog)
    with pytest.raises(AIOutputError):
        render_ai_selection(json.dumps({'items': [{'source_id': 'unknowns[0]', 'variant': 0}]}), catalog)


def test_adversarial_values_and_allowlist_fail_closed():
    context = {'known_facts': [
        {'claim': "FIX MsgType is 'SECRET-IGNORE'.", 'evidence_tags': [35]},
        {'field': {'tag': 38, 'value': 'SECRET', 'field_name': '<script>SECRET</script>'}},
        {'field': {'tag': 9999, 'value': 'SECRET'}},
        {'field': {'tag': 1, 'value': 'SECRET'}},
    ]}
    catalog = build_ai_catalog(context, {1, 38, 9999})
    assert 'SECRET' not in json.dumps(catalog)
    assert len(catalog) == 2


def test_input_limits_and_timeout_config():
    with pytest.raises(AIInputError):
        build_ai_catalog({'unknowns': ['x'] * 129})
    for timeout in [0, -1, float('inf'), 61]:
        with pytest.raises(AIConfigurationError):
            GeminiExplanationProvider(timeout=timeout)


class FakeResponse:
    def __init__(self, data, status=200):
        self.status = status
        self.raw = json.dumps(data).encode()
    def read(self, limit):
        return self.raw[:limit]


@pytest.mark.parametrize('data,status,valid', [
    ({'candidates': [{'finishReason': 'STOP', 'content': {'parts': [{'text': '{"items":[]}' }]}}]}, 200, True),
    ({'promptFeedback': {'blockReason': 'SAFETY'}}, 200, False),
    ({'candidates': [{'finishReason': 'MAX_TOKENS'}]}, 200, False),
    ({'candidates': []}, 200, False),
    ({'error': {'message': 'SECRET'}}, 403, False),
    ({'error': {'message': 'SECRET'}}, 429, False),
    ({'error': {'message': 'SECRET'}}, 500, False),
])
def test_http_transport_contract(monkeypatch, data, status, valid):
    seen = {}
    class Connection:
        def __init__(self, host, timeout):
            seen['host'], seen['timeout'] = host, timeout
        def request(self, method, path, body, headers):
            seen.update(method=method, path=path, headers=headers)
        def getresponse(self):
            return FakeResponse(data, status)
        def close(self):
            seen['closed'] = True
    monkeypatch.setattr('fix_explainer.ai.http.client.HTTPSConnection', Connection)
    if valid:
        assert gemini_transport('gemini-test', 'key', {}, 10) == '{"items":[]}'
    else:
        with pytest.raises(Exception) as info:
            gemini_transport('gemini-test', 'key', {}, 10)
        assert 'SECRET' not in str(info.value)
    assert seen['host'] == 'generativelanguage.googleapis.com'
    assert seen['path'] == '/v1beta/models/gemini-test:generateContent'
    assert seen['headers']['x-goog-api-key'] == 'key'
    assert 'key' not in seen['path']
    assert seen['closed']


def test_narrow_allowlist_also_removes_msgtype_claim():
    from fix_explainer import build_explanation_context, TemplateExplanationProvider
    context = build_explanation_context(message())
    assert not any(row['source_id'] == 'known_facts[0]' for row in build_ai_catalog(context, set()))
    assert 'MsgType' not in TemplateExplanationProvider(set()).summarize(context)


def test_failure_display_cited_and_private_even_for_malicious_msgtype():
    payload = b'8=FIX.4.4|9=0|35=SECRET-TYPE|38=987654|10=000|'
    parsed = split_message(payload, delimiter=b'|')
    def broken(*args):
        raise RuntimeError('SECRET-EXCEPTION')
    provider = GeminiExplanationProvider(model='gemini-test', api_key='key', transport=broken)
    error = ValidationError('INVALID_ENUM_VALUE', 'SECRET-DIAGNOSTIC', 'error', tag=54)
    result = explain_with_provider(parsed, provider, additional_errors=[error])
    assert result['fallback_used']
    assert 'SECRET' not in result['provider_summary']
    assert '987654' not in result['provider_summary']
    assert '[validation_errors[0]]' in result['provider_summary']
    assert '[unknowns[0]]' in result['provider_summary']
    assert result['fallback']['known_facts'][0]['claim'] == "FIX MsgType is 'SECRET-TYPE'."


def test_failure_preserves_generator_findings():
    class Broken:
        def summarize(self, context):
            raise RuntimeError()
    errors = (ValidationError('MISSING_REQUIRED_TAG', 'Missing quantity', 'error', tag=38) for _ in range(1))
    result = explain_with_provider(message(), Broken(), additional_errors=errors)
    assert result['fallback']['validation_errors'] == result['deterministic']['validation_errors']
    assert len(result['fallback']['validation_errors']) == 1


def test_http_socket_timeout_closes_connection(monkeypatch):
    seen = []
    class Connection:
        def __init__(self, *args, **kwargs):
            pass
        def request(self, *args, **kwargs):
            raise TimeoutError('SECRET')
        def close(self):
            seen.append('closed')
    monkeypatch.setattr('fix_explainer.ai.http.client.HTTPSConnection', Connection)
    from fix_explainer.ai import AITransportError
    with pytest.raises(AITransportError) as info:
        gemini_transport('gemini-test', 'key', {}, 10)
    assert 'SECRET' not in str(info.value)
    assert seen == ['closed']


def test_http_oversized_response_rejected(monkeypatch):
    from fix_explainer.ai import MAX_BYTES
    class Response:
        status = 200
        def read(self, limit):
            return b'x' * (MAX_BYTES + 1)
    class Connection:
        def __init__(self, *args, **kwargs):
            pass
        def request(self, *args, **kwargs):
            pass
        def getresponse(self):
            return Response()
        def close(self):
            pass
    monkeypatch.setattr('fix_explainer.ai.http.client.HTTPSConnection', Connection)
    with pytest.raises(AIOutputError):
        gemini_transport('gemini-test', 'key', {}, 10)
