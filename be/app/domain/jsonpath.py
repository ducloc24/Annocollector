"""A small JSONPath subset for field mapping: ``$``, ``.key``, ``['key']``, ``[n]``, ``[*]``."""

import re
from typing import Any

_TOKEN = re.compile(r"\.([A-Za-z_][\w-]*)|\['([^']+)'\]|\[(\d+)\]|\[(\*)\]")


class JsonPathError(ValueError):
    pass


def parse(path: str) -> list[str | int | None]:
    """Steps: str = key, int = index, None = wildcard."""
    if not path.startswith("$"):
        raise JsonPathError(f"Path must start with $: {path}")
    steps: list[str | int | None] = []
    pos = 1
    while pos < len(path):
        match = _TOKEN.match(path, pos)
        if not match:
            raise JsonPathError(f"Unsupported path syntax at {path[pos:]!r}")
        key, quoted, index, star = match.groups()
        if key is not None or quoted is not None:
            steps.append(key if key is not None else quoted)
        elif index is not None:
            steps.append(int(index))
        else:
            steps.append(None)
        pos = match.end()
    return steps


def has_wildcard(path: str) -> bool:
    return None in parse(path)


def find(data: Any, path: str) -> list[Any]:
    """All values matched by ``path``; missing keys simply match nothing."""
    current = [data]
    for step in parse(path):
        nxt: list[Any] = []
        for value in current:
            if step is None:
                if isinstance(value, list):
                    nxt.extend(value)
                elif isinstance(value, dict):
                    nxt.extend(value.values())
            elif isinstance(step, int):
                if isinstance(value, list) and -len(value) <= step < len(value):
                    nxt.append(value[step])
            elif isinstance(value, dict) and step in value:
                nxt.append(value[step])
        current = nxt
    return current


def first(data: Any, path: str) -> Any:
    found = find(data, path)
    return found[0] if found else None
