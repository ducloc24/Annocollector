"""Job rules inside a job config: how items are grouped and how work is handed out."""

from typing import Any

DEFAULT_JOB_RULES: dict[str, Any] = {
    "items_per_job": 1,
    "max_rework": 2,
    "lease_minutes": 120,
    "assignment_mode": "pull",
    "wip_limit_annotator": 3,
    "wip_limit_reviewer": 20,
    "review_rate": 1.0,
    "review_sla_hours": 24,
}

_INT_RANGES = {
    "items_per_job": (1, 200),
    "max_rework": (0, 5),
    "lease_minutes": (10, 24 * 60),
    "wip_limit_annotator": (1, 50),
    "wip_limit_reviewer": (1, 200),
    "review_sla_hours": (1, 24 * 14),
}


def normalize_rules(rules: Any) -> tuple[dict[str, Any], list[str]]:
    """Fill defaults and validate; return (rules, problems)."""
    if rules is None:
        rules = {}
    if not isinstance(rules, dict):
        return dict(DEFAULT_JOB_RULES), ["job_rules must be an object"]
    unknown = set(rules) - set(DEFAULT_JOB_RULES)
    merged = {**DEFAULT_JOB_RULES, **rules}
    errors = [f"Unknown rule '{k}'" for k in sorted(unknown)]
    for key, (low, high) in _INT_RANGES.items():
        v = merged[key]
        if isinstance(v, bool) or not isinstance(v, int) or not low <= v <= high:
            errors.append(f"{key} must be an integer between {low} and {high}")
    if merged["assignment_mode"] not in ("pull", "push_only"):
        errors.append("assignment_mode must be 'pull' or 'push_only'")
    if merged["review_rate"] != 1.0:
        errors.append("review_rate must be 1.0 for now (sampling is not supported yet)")
    return merged, errors


def validate_self_check(items: Any) -> list[str]:
    if not isinstance(items, list):
        return ["self_check must be a list of questions"]
    if len(items) > 20:
        return ["At most 20 self-check questions"]
    if not all(isinstance(q, str) and 0 < len(q.strip()) <= 300 for q in items):
        return ["Each self-check question must be 1-300 characters"]
    return []
