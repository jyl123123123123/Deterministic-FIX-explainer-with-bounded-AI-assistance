from copy import deepcopy

from fix_explainer import (
    TemplateExplanationProvider, build_explanation_context, explain_with_provider,
    split_message, ValidationError,
)


def message():
    return split_message(b'8=FIX.4.4|9=0|35=D|49=SECRET-SENDER|56=SECRET-TARGET|1=SECRET-ACCOUNT|11=SECRET-ORDER|55=AAPL|55=MSFT|54=1|9999=SECRET-CUSTOM|10=000|', delimiter=b'|')


def test_redaction_filtering_repeat_sources_and_no_mutation():
    context = build_explanation_context(message())
    before = deepcopy(context)
    result = TemplateExplanationProvider().summarize(context)
    assert context == before
    assert 'SECRET' not in result
    assert '9999' not in result
    assert 'AAPL' in result and 'MSFT' in result
    assert '[tag=55; ordinal=7]' in result
    assert '[tag=55; ordinal=8]' in result
    assert 'Buy' not in result  # no supplied enum definition
    assert '[tag=35; ordinal=2]' in result


def test_errors_unknowns_preserved_and_sensitive_text_withheld():
    error = ValidationError('BAD', 'SECRET-ACCOUNT', 'warning', tag=1, ordinal=5)
    result = explain_with_provider(message(), TemplateExplanationProvider(), additional_errors=[error])
    assert result['deterministic']['validation_errors'][0]['message'] == 'SECRET-ACCOUNT'
    assert 'SECRET' not in result['provider_summary']
    assert '[validation_errors[0]]' in result['provider_summary']
    assert '[unknowns[0]]' in result['provider_summary']
    assert not result['fallback_used']


def test_provider_exception_and_mutation_fall_back_with_findings():
    class Broken:
        def summarize(self, context):
            context['validation_errors'].clear()
            raise RuntimeError('SECRET')
    error = ValidationError('BAD', 'original finding', 'error', tag=38)
    result = explain_with_provider(message(), Broken(), additional_errors=[error])
    assert result['fallback_used']
    assert result['fallback_reason'] == 'Explanation failed (RuntimeError).'
    assert 'SECRET' not in result['fallback_reason']
    assert result['fallback']['validation_errors'] == result['deterministic']['validation_errors']
    assert result['fallback']['validation_errors'][0]['code'] == 'BAD'
    assert 'has validation errors' in result['provider_summary']


def test_legacy_context_marks_ambiguous_source_and_allowlist_can_only_narrow():
    context = {'known_facts': [{'field': {'tag': 55, 'value': 'AAPL'}},
                               {'field': {'tag': 1, 'value': 'SECRET'}}]}
    result = TemplateExplanationProvider({1, 55}).summarize(context)
    assert 'occurrence unavailable' in result
    assert 'SECRET' not in result
    assert 'AAPL' not in TemplateExplanationProvider(set()).summarize(context)


def test_empty_provider_output_falls_back():
    class Empty:
        def summarize(self, context):
            return ''
    assert explain_with_provider(message(), Empty())['fallback_used']


def test_unknown_free_text_not_disclosed_and_malformed_context_raises():
    import pytest
    provider = TemplateExplanationProvider()
    assert 'SECRET' not in provider.summarize({'unknowns': ['SECRET']})
    with pytest.raises(KeyError):
        provider.summarize({'known_facts': [{'field': {'tag': 55}}]})


def test_supplied_spec_enum_and_missing_field_record():
    from pathlib import Path
    from fix_explainer import load_orchestra
    spec = load_orchestra(Path(__file__).parent / 'fixtures' / 'fix_orchestra_subset.xml')
    error = ValidationError('MISSING_REQUIRED_TAG', 'Tag 38 missing', 'error', tag=38)
    result = explain_with_provider(message(), TemplateExplanationProvider(), spec, [error])
    summary = result['provider_summary']
    assert 'specification label "Buy"' in summary
    assert 'MISSING_REQUIRED_TAG' in summary
    assert '[validation_errors[0]]' in summary
    assert result['deterministic']['validation_errors'][0]['ordinal'] is None
