"""System settings that admins may change at runtime. Unknown keys are rejected."""

from typing import Any

SETTINGS: dict[str, dict[str, Any]] = {
    "appeal_window_days": {
        "default": 7,
        "min": 1,
        "max": 60,
        "label": "Số ngày annotator được khiếu nại sau khi bị reject",
    },
    "stuck_hours": {
        "default": 24,
        "min": 1,
        "max": 24 * 14,
        "label": "Số giờ ở một trạng thái chờ thì job bị coi là kẹt",
    },
    "max_upload_mb": {
        "default": 100,
        "min": 1,
        "max": 1000,
        "label": "Kích thước tối đa của file dataset (MB)",
    },
}


def defaults() -> dict[str, int]:
    return {key: spec["default"] for key, spec in SETTINGS.items()}


def validate(key: str, value: Any) -> str | None:
    """Problem with a setting value, or None when it is fine."""
    spec = SETTINGS.get(key)
    if spec is None:
        return f"Unknown setting {key}"
    if isinstance(value, bool) or not isinstance(value, int):
        return f"{key} must be an integer"
    if not spec["min"] <= value <= spec["max"]:
        return f"{key} must be between {spec['min']} and {spec['max']}"
    return None
