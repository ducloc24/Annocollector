import json
import uuid
from datetime import UTC, datetime, timedelta

import pytest

from app.core.exceptions import InvalidStateError
from app.domain import jsonpath
from app.domain.job_rules import DEFAULT_JOB_RULES, normalize_rules, validate_self_check
from app.domain.job_state import ensure_transition
from app.domain.label_schema import (
    DEFAULT_TOOL_CALL_SCHEMA,
    is_unsure,
    validate_schema,
    validate_value,
)
from app.domain.parsers import JSONL_CHAT, parse_failed
from app.models.project import Item
from app.models.work import JobConfig, JobStatus
from app.services.progress import acceptance_sample, summarize
from app.services.project import find_role_conflicts
from app.services.task import check_job_config, split_into_jobs
from app.services.work import validate_submission

CODES = {"WRONG_TOOL", "UNNECESSARY_CALL"}


def trajectory(**overrides):
    record = {
        "id": "t-1",
        "input": "Đặt vé HAN-SGN",
        "tools": [{"name": "search_flights"}],
        "steps": [
            {"type": "user", "content": "Đặt vé"},
            {"type": "tool_call", "tool": "search_flights", "args": {"origin": "HAN"}},
            {"type": "tool_result", "content": {"ok": True}},
            {"type": "tool_call", "tool": "book_flight", "args": {"id": "VN1"}},
            {"type": "assistant", "content": "Xong"},
        ],
    }
    record.update(overrides)
    return json.dumps(record, ensure_ascii=False)


# ---------- jsonpath ----------


def test_jsonpath():
    data = {"a": {"b": [{"c": 1}, {"c": 2}]}, "x y": 3}
    assert jsonpath.find(data, "$.a.b[*].c") == [1, 2]
    assert jsonpath.first(data, "$.a.b[1].c") == 2
    assert jsonpath.first(data, "$['x y']") == 3
    assert jsonpath.find(data, "$.missing.key") == []
    with pytest.raises(jsonpath.JsonPathError):
        jsonpath.parse("a.b")
    with pytest.raises(jsonpath.JsonPathError):
        jsonpath.parse("$.a[?(@.x)]")


# ---------- parser ----------


def test_parser_builds_steps_and_targets():
    result = JSONL_CHAT.parse([trajectory()], {}, None)
    assert not result.errors
    item = result.items[0]
    assert item.external_ref == "t-1"
    assert item.payload["targets"] == ["s2", "s4"]
    assert item.payload["steps"][1] == {
        "id": "s2", "type": "tool_call", "tool": "search_flights", "args": {"origin": "HAN"}
    }
    assert item.payload["steps"][2]["content"] == '{"ok": true}'


def test_parser_reports_errors_by_line():
    lines = [trajectory(), "{bad json", "", trajectory(steps=[{"type": "user", "content": "x"}]),
             trajectory(steps=[{"type": "weird"}])]
    result = JSONL_CHAT.parse(lines, {}, None)
    assert len(result.items) == 1
    assert [(e.line, e.code) for e in result.errors] == [
        (2, "invalid_json"), (4, "no_tool_calls"), (5, "bad_step_type")
    ]
    assert result.lines_total == 4
    assert parse_failed(result)


def test_parser_field_mapping():
    line = json.dumps({"q": "hi", "trace": [{"kind": "tool_call", "name": "f", "arguments": {}}]})
    result = JSONL_CHAT.parse([line], {"user_message": "$.q", "steps": "$.trace[*]",
                                       "step_type": "$.kind", "tool_name": "$.name",
                                       "tool_args": "$.arguments"}, None)
    assert result.items[0].payload["user_message"] == "hi"
    assert result.items[0].payload["targets"] == ["s1"]


def test_parser_rejects_bad_mapping():
    from app.domain.parsers import ParserOptionsError

    with pytest.raises(ParserOptionsError):
        JSONL_CHAT.parse([trajectory()], {"steps": "steps"}, None)
    with pytest.raises(ParserOptionsError):
        JSONL_CHAT.parse([trajectory()], {"unknown": "$.x"}, None)


# ---------- label schema ----------


def test_default_schema_is_valid():
    assert validate_schema(DEFAULT_TOOL_CALL_SCHEMA) == []


def test_schema_problems():
    assert validate_schema({"fields": []})
    assert validate_schema({"fields": [{"name": "a", "type": "enum"}]})
    assert validate_schema({"fields": [{"name": "a", "type": "text", "visible_if": {"field": "b"}}]})
    assert validate_schema({"fields": [{"name": "a", "type": "text"}, {"name": "a", "type": "text"}]})


def test_value_rules():
    s = DEFAULT_TOOL_CALL_SCHEMA
    value, errors = validate_value(s, {"verdict": "correct", "reason_codes": ["X"]}, CODES)
    assert errors == [] and value == {"verdict": "correct"}  # hidden field dropped
    _, errors = validate_value(s, {"verdict": "incorrect"}, CODES)
    assert errors == ["reason_codes is required"]
    _, errors = validate_value(s, {"verdict": "incorrect", "reason_codes": ["NOPE"]}, CODES)
    assert errors == ["reason_codes has an invalid option"]
    value, errors = validate_value(
        s, {"verdict": "incorrect", "reason_codes": ["WRONG_TOOL", "WRONG_TOOL"]}, CODES
    )
    assert not errors and value["reason_codes"] == ["WRONG_TOOL"]
    _, errors = validate_value(s, {"verdict": "maybe"}, CODES)
    assert errors == ["verdict has an invalid option"]
    assert is_unsure(s, {"verdict": "unsure"}) and not is_unsure(s, {"verdict": "correct"})


# ---------- job rules and configs ----------


def test_job_rules():
    rules, errors = normalize_rules({"items_per_job": 5})
    assert not errors and rules["items_per_job"] == 5 and rules["max_rework"] == 2
    assert normalize_rules({"items_per_job": 0})[1]
    assert normalize_rules({"review_rate": 0.3})[1]
    assert normalize_rules({"bogus": 1})[1]
    assert validate_self_check(["ok"]) == [] and validate_self_check([""])
    _, errors = check_job_config("image_bbox", DEFAULT_TOOL_CALL_SCHEMA, {}, [])
    assert errors == ["Unknown item_type image_bbox"]


def test_split_into_jobs():
    ids = [uuid.uuid4() for _ in range(5)]
    assert [len(g) for g in split_into_jobs(ids, 2)] == [2, 2, 1]


# ---------- state machine ----------


def test_state_machine():
    ensure_transition("unassigned", JobStatus.IN_PROGRESS)
    ensure_transition("in_review", JobStatus.REJECTED)
    with pytest.raises(InvalidStateError) as exc:
        ensure_transition("assigned", JobStatus.SUBMITTED)
    assert exc.value.details["allowed"]
    with pytest.raises(InvalidStateError):
        ensure_transition("submitted", JobStatus.ACCEPTED)


# ---------- submission ----------


def make_item(targets):
    return Item(id=uuid.uuid4(), payload={"targets": targets}, ordinal=1, item_type="tool_call")


def test_validate_submission():
    config = JobConfig(item_type="tool_call", label_schema=DEFAULT_TOOL_CALL_SCHEMA)
    item = make_item(["s2", "s4"])
    ok = [
        {"item_id": str(item.id), "target": "s2", "value": {"verdict": "correct"}},
        {"item_id": str(item.id), "target": "s4", "value": {"verdict": "unsure", "note": "?"}},
    ]
    cleaned, errors = validate_submission(config, [item], ok, CODES)
    assert errors == [] and [c["is_unsure"] for c in cleaned] == [False, True]

    _, errors = validate_submission(config, [item], ok[:1], CODES)
    assert errors and "not labelled" in errors[-1]
    _, errors = validate_submission(config, [item], ok + ok[:1], CODES)
    assert any("twice" in e for e in errors)
    bad = [{**ok[0], "target": "s9"}, ok[1]]
    _, errors = validate_submission(config, [item], bad, CODES)
    assert any("unknown" in e for e in errors)


# ---------- teams ----------


def test_role_conflicts():
    a, b, t1, t2 = uuid.uuid4(), uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    rows = [(a, "annotator", t1), (a, "reviewer", t2), (b, "annotator", t1), (b, "annotator", t2)]
    assert find_role_conflicts(rows) == {a}


# ---------- progress ----------


def test_summary():
    now = datetime(2026, 11, 1, tzinfo=UTC)
    counts = {"accepted": 3, "accepted_with_fix": 1, "submitted": 2, "unassigned": 4}
    closed = [(now - timedelta(hours=h + 1), now - timedelta(days=d), r)
              for h, d, r in [(2, 1, 0), (4, 2, 1), (10, 3, 0), (20, 9, 0)]]
    s = summarize(counts, closed, now)
    assert s["jobs_total"] == 10
    assert s["completion_rate"] == 0.4
    assert s["backlog"] == 6
    assert s["throughput_per_day"] == round(3 / 7, 1)
    assert s["first_pass_rate"] == 0.75


def test_acceptance_sample_is_stable():
    task = uuid.uuid4()
    jobs = [uuid.uuid4() for _ in range(100)]
    first = acceptance_sample(task, jobs)
    assert first == acceptance_sample(task, jobs)
    assert len(first) == 5 and set(first) <= set(jobs)
    assert acceptance_sample(task, []) == []
