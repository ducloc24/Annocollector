"""Label schema: declares the label fields; drives the form in fe and validation here.

Supported field types: enum, multi_select, text, number, boolean.
``visible_if`` supports a single ``{"field": ..., "equals": ...}`` condition.
"""

from typing import Any

FIELD_TYPES = ("enum", "multi_select", "text", "number", "boolean")
OPTIONS_FROM_REASON_CODES = "reason_codes"
MAX_FIELDS = 20

DEFAULT_TOOL_CALL_SCHEMA: dict[str, Any] = {
    "fields": [
        {
            "name": "verdict",
            "label": "Tool call này",
            "type": "enum",
            "required": True,
            "options": ["correct", "incorrect", "unsure"],
        },
        {
            "name": "reason_codes",
            "label": "Lý do",
            "type": "multi_select",
            "required": True,
            "options_from": OPTIONS_FROM_REASON_CODES,
            "visible_if": {"field": "verdict", "equals": "incorrect"},
        },
        {"name": "note", "label": "Ghi chú", "type": "text", "required": False, "max_length": 1000},
    ],
    "unsure_field": {"field": "verdict", "equals": "unsure"},
}


def validate_schema(schema: Any) -> list[str]:
    """Problems with the schema itself (empty list means valid)."""
    if not isinstance(schema, dict) or not isinstance(schema.get("fields"), list):
        return ["Schema must be an object with a 'fields' list"]
    fields = schema["fields"]
    errors: list[str] = []
    if not fields:
        errors.append("At least one field is required")
    if len(fields) > MAX_FIELDS:
        errors.append(f"At most {MAX_FIELDS} fields")
    names: set[str] = set()
    for index, f in enumerate(fields):
        where = f"fields[{index}]"
        if not isinstance(f, dict):
            errors.append(f"{where} must be an object")
            continue
        name = f.get("name")
        if not isinstance(name, str) or not name.isidentifier():
            errors.append(f"{where}.name must be an identifier")
            continue
        if name in names:
            errors.append(f"{where}.name '{name}' is duplicated")
        names.add(name)
        ftype = f.get("type")
        if ftype not in FIELD_TYPES:
            errors.append(f"{where}.type must be one of {FIELD_TYPES}")
        if ftype in ("enum", "multi_select"):
            options = f.get("options")
            from_codes = f.get("options_from") == OPTIONS_FROM_REASON_CODES
            if not from_codes and (
                not isinstance(options, list)
                or not options
                or not all(isinstance(o, str) and o for o in options)
            ):
                errors.append(f"{where} needs non-empty string 'options' or options_from")
        cond = f.get("visible_if")
        if cond is not None and (
            not isinstance(cond, dict) or cond.get("field") not in names - {name}
        ):
            errors.append(f"{where}.visible_if must reference an earlier field")
    unsure = schema.get("unsure_field")
    if unsure is not None and (not isinstance(unsure, dict) or unsure.get("field") not in names):
        errors.append("unsure_field must reference a field")
    return errors


def _visible(field: dict[str, Any], value: dict[str, Any]) -> bool:
    cond = field.get("visible_if")
    return cond is None or value.get(cond["field"]) == cond.get("equals")


def _options(field: dict[str, Any], reason_codes: set[str]) -> set[str]:
    if field.get("options_from") == OPTIONS_FROM_REASON_CODES:
        return reason_codes
    return set(field.get("options", []))


def validate_value(
    schema: dict[str, Any], value: Any, reason_codes: set[str]
) -> tuple[dict[str, Any], list[str]]:
    """Return the cleaned label (hidden/unknown fields dropped) and the problems found."""
    if not isinstance(value, dict):
        return {}, ["Label must be an object"]
    cleaned: dict[str, Any] = {}
    errors: list[str] = []
    for f in schema["fields"]:
        name = f["name"]
        if not _visible(f, {**value, **cleaned}):
            continue
        v = value.get(name)
        empty = v is None or v == "" or v == []
        if empty:
            if f.get("required"):
                errors.append(f"{name} is required")
            continue
        ftype = f["type"]
        if ftype == "enum":
            if v not in _options(f, reason_codes):
                errors.append(f"{name} has an invalid option")
                continue
        elif ftype == "multi_select":
            allowed = _options(f, reason_codes)
            if not isinstance(v, list) or not all(o in allowed for o in v):
                errors.append(f"{name} has an invalid option")
                continue
            v = sorted(set(v))
        elif ftype == "text":
            if not isinstance(v, str):
                errors.append(f"{name} must be text")
                continue
            if len(v) > int(f.get("max_length", 5000)):
                errors.append(f"{name} is too long")
                continue
        elif ftype == "number":
            if isinstance(v, bool) or not isinstance(v, int | float):
                errors.append(f"{name} must be a number")
                continue
        elif ftype == "boolean" and not isinstance(v, bool):
            errors.append(f"{name} must be true or false")
            continue
        cleaned[name] = v
    return cleaned, errors


def is_unsure(schema: dict[str, Any], value: dict[str, Any]) -> bool:
    cond = schema.get("unsure_field")
    if not isinstance(cond, dict):
        return False
    return bool(value.get(cond["field"]) == cond.get("equals"))
