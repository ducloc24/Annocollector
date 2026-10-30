import random
import uuid
from datetime import UTC, datetime

import pytest

from app.core.exceptions import InvalidStateError
from app.domain import quality as q
from app.domain.job_rules import normalize_rules
from app.domain.job_state import ensure_transition
from app.domain.settings_catalog import defaults, validate
from app.models.work import JobStatus


def test_review_sampling_rules():
    rng = random.Random(1)
    assert q.should_review(1.0, is_gold=False, has_unsure=False, rework_count=0, rng=rng)
    # Anything worth a second look is always reviewed.
    for kwargs in ({"is_gold": True}, {"has_unsure": True}, {"rework_count": 1}):
        base = {"is_gold": False, "has_unsure": False, "rework_count": 0, **kwargs}
        assert q.should_review(0.05, rng=rng, **base)
    picked = sum(
        q.should_review(0.3, is_gold=False, has_unsure=False, rework_count=0, rng=random.Random(i))
        for i in range(2000)
    )
    assert 450 < picked < 750


def test_review_rate_is_validated():
    assert normalize_rules({"review_rate": 0.3})[1] == []
    assert normalize_rules({"review_rate": 0.01})[1]
    assert normalize_rules({"review_rate": 1.5})[1]
    assert normalize_rules({"review_rate": True})[1]


def test_gold_comparison_ignores_notes_and_order():
    expected = {
        ("i", "s1"): {"verdict": "incorrect", "reason_codes": ["B", "A"], "note": "x"},
        ("i", "s2"): {"verdict": "correct"},
    }
    given = {
        ("i", "s1"): {"verdict": "incorrect", "reason_codes": ["A", "B"], "note": "other"},
        ("i", "s2"): {"verdict": "incorrect", "reason_codes": ["A"]},
    }
    assert q.gold_accuracy(expected, given) == (1, 2)
    assert q.gold_accuracy(expected, {}) == (0, 2)
    assert q.gold_accuracy({}, given) == (0, 0)


def test_annotator_stats_and_ratio():
    f = q.AnnotatorFacts(
        user_id=uuid.uuid4(),
        closed=4,
        first_pass=3,
        rework_total=2,
        reviews=5,
        rejected_reviews=1,
        gold_correct=9,
        gold_total=10,
    )
    row = q.annotator_stats([f])[0]
    assert row["first_pass_rate"] == 0.75
    assert row["avg_rework"] == 0.5
    assert row["reject_rate"] == 0.2
    assert row["gold_accuracy"] == 0.9
    empty = q.annotator_stats([q.AnnotatorFacts(user_id=uuid.uuid4())])[0]
    assert empty["first_pass_rate"] is None and empty["gold_accuracy"] is None


def test_top_reason_codes_and_trend():
    rows = [("A", "major"), ("B", "minor"), ("A", "major"), ("A", "major"), ("B", "minor")]
    top = q.top_reason_codes(rows, limit=1)
    assert top == [{"reason_code": "A", "count": 3, "severity": "major"}]
    trend = q.weekly_trend(
        [
            (datetime(2026, 11, 2, tzinfo=UTC), 0),
            (datetime(2026, 11, 3, tzinfo=UTC), 1),
            (datetime(2026, 11, 10, tzinfo=UTC), 0),
        ]
    )
    assert [t["jobs"] for t in trend] == [2, 1]
    assert trend[0]["first_pass_rate"] == 0.5


def test_override_and_sampling_transitions():
    ensure_transition(JobStatus.SUBMITTED, JobStatus.ACCEPTED)
    ensure_transition(JobStatus.REJECTED, JobStatus.ACCEPTED)
    ensure_transition(JobStatus.ACCEPTED, JobStatus.REJECTED)
    with pytest.raises(InvalidStateError):
        ensure_transition(JobStatus.IN_PROGRESS, JobStatus.ACCEPTED)


def test_settings_catalog():
    assert defaults() == {"appeal_window_days": 7, "stuck_hours": 24, "max_upload_mb": 100}
    assert validate("stuck_hours", 48) is None
    assert validate("stuck_hours", 0)
    assert validate("stuck_hours", "48")
    assert validate("stuck_hours", True)
    assert validate("nope", 1)
