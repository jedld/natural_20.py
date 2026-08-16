"""Parse model JSON even when wrapped in markdown fences, prose, or truncated."""

from __future__ import annotations

import json
import re
from typing import Any

_FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.S | re.I)


def parse_json_object(text: str) -> dict[str, Any]:
    if not text or not str(text).strip():
        raise ValueError("empty model response")
    raw = str(text).strip()
    fenced = _FENCE.search(raw)
    if fenced:
        raw = fenced.group(1).strip()
    try:
        return _coerce_object(json.loads(raw))
    except json.JSONDecodeError:
        start = raw.find("{")
        if start < 0:
            raise
        snippet = raw[start:]
        try:
            end = snippet.rfind("}")
            if end > 0:
                return _coerce_object(json.loads(snippet[: end + 1]))
        except json.JSONDecodeError:
            pass
        repaired = repair_json_object(snippet)
        return _coerce_object(json.loads(repaired))


def repair_json_object(text: str) -> str:
    """Close truncated JSON objects/arrays (and an open string) so json.loads can run."""
    snippet = str(text).strip()
    start = snippet.find("{")
    if start < 0:
        start = snippet.find("[")
    if start < 0:
        raise ValueError("no JSON object to repair")
    snippet = snippet[start:]
    stack: list[str] = []
    in_string = False
    escape = False
    for ch in snippet:
        if in_string:
            if escape:
                escape = False
                continue
            if ch == "\\":
                escape = True
                continue
            if ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
            continue
        if ch == "{":
            stack.append("}")
        elif ch == "[":
            stack.append("]")
        elif ch in "}]":
            if stack and stack[-1] == ch:
                stack.pop()
    out = snippet
    if in_string:
        out += '"'
    stripped = out.rstrip()
    if stripped.endswith(","):
        out = stripped[:-1]
    out += "".join(reversed(stack))
    return out


def _coerce_object(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, list) and value and isinstance(value[0], dict):
        return value[0]
    raise ValueError("JSON root is not an object")
