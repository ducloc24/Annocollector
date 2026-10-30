"""Parser registry: turn an uploaded file into items. Config lives in the DB, code lives here."""

import json
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from typing import Any

from app.domain import jsonpath

STEP_TYPES = ("user", "thought", "tool_call", "tool_result", "assistant")


@dataclass
class ParsedItem:
    ordinal: int
    external_ref: str | None
    payload: dict[str, Any]


@dataclass
class ParseError:
    line: int
    code: str
    message: str

    def as_dict(self) -> dict[str, Any]:
        return {"line": self.line, "code": self.code, "message": self.message}


@dataclass
class ParseResult:
    items: list[ParsedItem] = field(default_factory=list)
    errors: list[ParseError] = field(default_factory=list)
    lines_total: int = 0

    def report(self, max_errors: int = 50) -> dict[str, Any]:
        return {
            "lines_total": self.lines_total,
            "lines_ok": len(self.items),
            "error_count": len(self.errors),
            "errors": [e.as_dict() for e in self.errors[:max_errors]],
        }


@dataclass(frozen=True)
class Parser:
    name: str
    version: str
    item_type: str
    description: str
    default_options: dict[str, str]
    parse: Callable[[Iterable[str], dict[str, str], int | None], ParseResult]


class ParserOptionsError(ValueError):
    pass


JSONL_CHAT_DEFAULTS = {
    "id": "$.id",
    "user_message": "$.input",
    "tools": "$.tools[*]",
    "steps": "$.steps[*]",
    "step_type": "$.type",
    "step_content": "$.content",
    "tool_name": "$.tool",
    "tool_args": "$.args",
}


def _text(value: Any) -> str:
    if value is None:
        return ""
    return value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)


def _validate_options(options: dict[str, str]) -> dict[str, str]:
    merged = {**JSONL_CHAT_DEFAULTS, **{k: v for k, v in options.items() if v}}
    unknown = set(merged) - set(JSONL_CHAT_DEFAULTS)
    if unknown:
        raise ParserOptionsError(f"Unknown mapping keys: {sorted(unknown)}")
    for key, path in merged.items():
        try:
            jsonpath.parse(path)
        except jsonpath.JsonPathError as exc:
            raise ParserOptionsError(f"{key}: {exc}") from None
    return merged


def _parse_record(record: Any, m: dict[str, str]) -> dict[str, Any]:
    if not isinstance(record, dict):
        raise ValueError("not_object|Line is not a JSON object")
    raw_steps = jsonpath.find(record, m["steps"])
    if not raw_steps:
        raise ValueError(f"missing_steps|No steps found at {m['steps']}")
    steps: list[dict[str, Any]] = []
    targets: list[str] = []
    for index, raw in enumerate(raw_steps, start=1):
        step_type = jsonpath.first(raw, m["step_type"])
        if step_type not in STEP_TYPES:
            raise ValueError(
                f"bad_step_type|Step {index} has type {step_type!r}; expected one of {STEP_TYPES}"
            )
        step_id = f"s{index}"
        if step_type == "tool_call":
            tool = jsonpath.first(raw, m["tool_name"])
            if not tool:
                raise ValueError(f"missing_tool|Step {index} has no tool name")
            args = jsonpath.first(raw, m["tool_args"])
            steps.append({"id": step_id, "type": step_type, "tool": str(tool), "args": args or {}})
            targets.append(step_id)
        else:
            content = _text(jsonpath.first(raw, m["step_content"]))
            steps.append({"id": step_id, "type": step_type, "content": content})
    if not targets:
        raise ValueError("no_tool_calls|Trajectory has no tool call to evaluate")
    tools = []
    for tool in jsonpath.find(record, m["tools"]):
        if isinstance(tool, dict):
            tools.append(tool)
    return {
        "user_message": _text(jsonpath.first(record, m["user_message"])),
        "tools": tools,
        "steps": steps,
        "targets": targets,
    }


def parse_jsonl_chat(
    lines: Iterable[str], options: dict[str, str], limit: int | None = None
) -> ParseResult:
    mapping = _validate_options(options)
    result = ParseResult()
    for number, line in enumerate(lines, start=1):
        if limit is not None and len(result.items) + len(result.errors) >= limit:
            break
        if not line.strip():
            continue
        result.lines_total += 1
        try:
            record = json.loads(line)
            payload = _parse_record(record, mapping)
        except json.JSONDecodeError as exc:
            result.errors.append(ParseError(number, "invalid_json", str(exc)))
            continue
        except ValueError as exc:
            code, _, message = str(exc).partition("|")
            result.errors.append(ParseError(number, code, message or code))
            continue
        ref = jsonpath.first(record, mapping["id"])
        result.items.append(
            ParsedItem(
                ordinal=len(result.items) + 1,
                external_ref=str(ref)[:200] if ref is not None else None,
                payload=payload,
            )
        )
    return result


JSONL_CHAT = Parser(
    name="jsonl_chat",
    version="1.0.0",
    item_type="tool_call",
    description="JSONL, mỗi dòng một trajectory; ánh xạ trường bằng JSONPath",
    default_options=JSONL_CHAT_DEFAULTS,
    parse=parse_jsonl_chat,
)

PARSERS: dict[str, Parser] = {JSONL_CHAT.name: JSONL_CHAT}


def get_parser(name: str) -> Parser | None:
    return PARSERS.get(name)


def parse_failed(result: ParseResult, max_error_ratio: float = 0.1) -> bool:
    """Reject the upload when nothing parsed or too many lines failed."""
    if not result.items:
        return True
    return len(result.errors) > max_error_ratio * max(result.lines_total, 1)
