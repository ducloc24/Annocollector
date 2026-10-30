"""Item type registry. Adding a data type means adding an entry here (and a renderer in fe)."""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ItemType:
    name: str
    description: str
    # Parts of one item that receive their own label (e.g. tool-call step ids).
    targets: Callable[[dict[str, Any]], list[str]]


def _tool_call_targets(payload: dict[str, Any]) -> list[str]:
    return [str(t) for t in payload.get("targets", [])]


TOOL_CALL = ItemType(
    name="tool_call",
    description="Trajectory của agent; mỗi tool call là một target cần đánh giá",
    targets=_tool_call_targets,
)

ITEM_TYPES: dict[str, ItemType] = {TOOL_CALL.name: TOOL_CALL}


def get_item_type(name: str) -> ItemType | None:
    return ITEM_TYPES.get(name)
