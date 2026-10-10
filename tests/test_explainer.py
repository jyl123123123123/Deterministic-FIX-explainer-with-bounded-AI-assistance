from pathlib import Path

from fix_explainer import (
    build_explanation_context,
    explain_deterministically,
    explain_with_provider,
    load_orchestra,
    split_message,
)


FIXTURE_DIR = Path(__file__).parent / "fixtures"


def load_inputs():
    payload = (FIXTURE_DIR / "new_order_single.fix").read_bytes()
    message = split_message(payload.rstrip(b"\r\n").replace(b"|", b"\x01"))
    specification = load_orchestra(FIXTURE_DIR / "fix_orchestra_subset.xml")
    return message, specification


def test_deterministic_explainer_cites_tags_and_preserves_unknowns() -> None:
    message, specification = load_inputs()

    result = explain_deterministically(message, specification)

    assert result["summary"] == "The FIX message is type 'D' and passed available checks."
    assert result["known_facts"][1]["evidence_tags"] == [35]
    assert result["known_facts"][1]["claim"] == "Message purpose is NewOrderSingle."
    assert result["unknowns"] == [
        "Business outcome and causality are not determined by this message alone."
    ]


def test_provider_receives_structured_context_not_raw_payload() -> None:
    message, specification = load_inputs()

    class RecordingProvider:
        def __init__(self) -> None:
            self.context = None

        def summarize(self, context):
            self.context = context
            return "bounded summary"

    provider = RecordingProvider()
    result = explain_with_provider(message, provider, specification)

    assert result["provider_summary"] == "bounded summary"
    assert provider.context is not None
    assert "raw_payload" not in provider.context
    assert provider.context["known_facts"][0]["evidence_tags"] == [35]


def test_context_can_carry_deterministic_validation_errors() -> None:
    message, specification = load_inputs()
    context = build_explanation_context(message, specification, message.errors)

    assert context["validation_errors"] == []