"""Small, deterministic FIX Orchestra XML specification loader."""

from dataclasses import dataclass
from pathlib import Path
import xml.etree.ElementTree as ElementTree


@dataclass(frozen=True)
class FieldSpec:
    tag: int
    name: str
    type_name: str
    enum_values: dict[str, str]


@dataclass(frozen=True)
class MessageSpec:
    msg_type: str
    name: str
    required_fields: frozenset[int]
    allowed_fields: frozenset[int]


@dataclass(frozen=True)
class FixSpecification:
    version: str
    fields: dict[int, FieldSpec]
    messages: dict[str, MessageSpec]


def load_orchestra(source: bytes | str | Path) -> FixSpecification:
    """Load fields, code sets, and message field requirements from Orchestra XML."""
    root = _parse_source(source)
    version = root.attrib.get("version", "unknown")
    code_sets = _load_code_sets(root)
    fields = _load_fields(root, code_sets)
    messages = _load_messages(root, fields)
    return FixSpecification(version=version, fields=fields, messages=messages)


def _parse_source(source: bytes | str | Path) -> ElementTree.Element:
    if isinstance(source, Path):
        return ElementTree.parse(source).getroot()
    if isinstance(source, bytes):
        return ElementTree.fromstring(source)
    source_path = Path(source)
    if source_path.exists():
        return ElementTree.parse(source_path).getroot()
    return ElementTree.fromstring(source)


def _load_code_sets(root: ElementTree.Element) -> dict[str, dict[str, str]]:
    code_sets: dict[str, dict[str, str]] = {}
    for element in root.iter():
        if _local_name(element.tag) != "codeSet":
            continue
        name = element.attrib.get("name")
        if not name:
            continue
        code_sets[name] = {
            code.attrib["value"]: code.attrib.get("name", "")
            for code in element
            if _local_name(code.tag) == "code" and "value" in code.attrib
        }
    return code_sets


def _load_fields(
    root: ElementTree.Element,
    code_sets: dict[str, dict[str, str]],
) -> dict[int, FieldSpec]:
    fields: dict[int, FieldSpec] = {}
    for element in root.iter():
        if _local_name(element.tag) != "field" or "id" not in element.attrib:
            continue
        tag = int(element.attrib["id"])
        code_set_name = element.attrib.get("codeSet") or element.attrib.get("codeSetName")
        fields[tag] = FieldSpec(
            tag=tag,
            name=element.attrib.get("name", str(tag)),
            type_name=element.attrib.get("type", element.attrib.get("typeName", "String")),
            enum_values=dict(code_sets.get(code_set_name, {})),
        )
    return fields


def _load_messages(
    root: ElementTree.Element,
    fields: dict[int, FieldSpec],
) -> dict[str, MessageSpec]:
    fields_by_name = {field.name: field for field in fields.values()}
    messages: dict[str, MessageSpec] = {}
    for element in root.iter():
        if _local_name(element.tag) != "message":
            continue
        msg_type = element.attrib.get("msgType")
        name = element.attrib.get("name")
        if not msg_type or not name:
            continue
        allowed: set[int] = set()
        required: set[int] = set()
        for field_ref in element.iter():
            if _local_name(field_ref.tag) != "field":
                continue
            field = _resolve_field(field_ref, fields, fields_by_name)
            if field is None:
                continue
            allowed.add(field.tag)
            if field_ref.attrib.get("required", "false").lower() == "true":
                required.add(field.tag)
        messages[msg_type] = MessageSpec(
            msg_type=msg_type,
            name=name,
            required_fields=frozenset(required),
            allowed_fields=frozenset(allowed),
        )
    return messages


def _resolve_field(
    element: ElementTree.Element,
    fields: dict[int, FieldSpec],
    fields_by_name: dict[str, FieldSpec],
) -> FieldSpec | None:
    if "id" in element.attrib:
        return fields.get(int(element.attrib["id"]))
    if "name" in element.attrib:
        return fields_by_name.get(element.attrib["name"])
    return None


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]