"""Quality maths, kept free of the database so it can be unit tested."""

import random
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any

IGNORED_LABEL_KEYS = frozenset({"note"})


def should_review(
    rate: float,
    *,
    is_gold: bool,
    has_unsure: bool,
    rework_count: int,
    rng: random.Random | None = None,
) -> bool:
    """Review sampling: jobs worth a second look are always reviewed, the rest by chance."""
    if rate >= 1.0 or is_gold or has_unsure or rework_count > 0:
        return True
    return (rng or random).random() < rate


def comparable(value: Mapping[str, Any]) -> dict[str, Any]:
    """A label without free-text keys, with multi-selects order-independent."""
    cleaned: dict[str, Any] = {}
    for key, v in value.items():
        if key in IGNORED_LABEL_KEYS:
            continue
        cleaned[key] = sorted(v) if isinstance(v, list) else v
    return cleaned


def gold_accuracy(
    expected: Mapping[tuple[str, str | None], Mapping[str, Any]],
    given: Mapping[tuple[str, str | None], Mapping[str, Any]],
) -> tuple[int, int]:
    """(correct, total) over the expected targets."""
    correct = sum(
        1
        for key, exp in expected.items()
        if key in given and comparable(given[key]) == comparable(exp)
    )
    return correct, len(expected)


def ratio(part: int, whole: int) -> float | None:
    return round(part / whole, 3) if whole else None


@dataclass
class AnnotatorFacts:
    user_id: Any
    closed: int = 0
    first_pass: int = 0
    rework_total: int = 0
    rejected_reviews: int = 0
    reviews: int = 0
    gold_correct: int = 0
    gold_total: int = 0


def annotator_stats(facts: Iterable[AnnotatorFacts]) -> list[dict[str, Any]]:
    return [
        {
            "user_id": str(f.user_id),
            "jobs_closed": f.closed,
            "first_pass_rate": ratio(f.first_pass, f.closed),
            "avg_rework": round(f.rework_total / f.closed, 2) if f.closed else None,
            "reject_rate": ratio(f.rejected_reviews, f.reviews),
            "gold_accuracy": ratio(f.gold_correct, f.gold_total),
        }
        for f in facts
    ]


def top_reason_codes(rows: Iterable[tuple[str, str]], limit: int = 8) -> list[dict[str, Any]]:
    """rows: (reason_code, severity)."""
    counts = Counter(code for code, _ in rows)
    severities = {code: sev for code, sev in rows}
    return [
        {"reason_code": code, "count": n, "severity": severities[code]}
        for code, n in counts.most_common(limit)
    ]


def weekly_trend(closed: Iterable[tuple[datetime, int]]) -> list[dict[str, Any]]:
    """(closed_at, rework_count) -> first-pass rate per ISO week."""
    weeks: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    for closed_at, rework in closed:
        year, week, _ = closed_at.isocalendar()
        bucket = weeks[f"{year}-W{week:02d}"]
        bucket[1] += 1
        bucket[0] += 1 if rework == 0 else 0
    return [
        {"week": w, "jobs": total, "first_pass_rate": ratio(first, total)}
        for w, (first, total) in sorted(weeks.items())
    ]
