from pathlib import Path

from fix_explainer import load_orchestra


SPEC_PATH = Path(__file__).parent / "fixtures" / "fix_orchestra_subset.xml"


def test_load_orchestra_reads_fields_enums_and_message_requirements() -> None:
    specification = load_orchestra(SPEC_PATH)

    assert specification.version == "1.0"
    assert specification.fields[54].name == "Side"
    assert specification.fields[54].enum_values == {"1": "Buy", "2": "Sell"}
    assert specification.fields[40].enum_values == {"2": "Limit"}
    assert specification.messages["D"].name == "NewOrderSingle"
    assert specification.messages["D"].required_fields == frozenset({11, 38, 40, 54, 55})
    assert specification.messages["D"].allowed_fields == frozenset({11, 38, 40, 54, 55})


def test_load_orchestra_accepts_xml_bytes() -> None:
    specification = load_orchestra(SPEC_PATH.read_bytes())

    assert set(specification.fields) == {11, 38, 40, 54, 55}