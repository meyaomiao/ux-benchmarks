"""Tolerant JSON extraction for LLM responses.

LLMs frequently return JSON that is *almost* valid but breaks a strict parser:
  - wrapped in ```json fences or prose
  - trailing commas
  - unescaped ASCII double quotes *inside* string values (very common when the
    value is Chinese prose that quotes a UI label, e.g.  "reasoning": "点击"邀请"按钮")

`extract_json` tries increasingly aggressive strategies and only raises if all fail.
"""
from __future__ import annotations

import json
import re
from typing import Any

_FENCE = re.compile(r"```(?:json)?\s*(\{.*?\}|\[.*?\])\s*```", re.DOTALL)
_BRACES = re.compile(r"\{.*\}", re.DOTALL)


def _candidate_region(raw: str) -> str:
    """Isolate the JSON-looking region: prefer a fenced block, else first {...}."""
    m = _FENCE.search(raw)
    if m:
        return m.group(1)
    m = _BRACES.search(raw)
    return m.group(0) if m else raw


def _strip_trailing_commas(s: str) -> str:
    return re.sub(r",\s*([}\]])", r"\1", s)


def _escape_inner_quotes(s: str) -> str:
    """Escape ASCII double quotes that appear *inside* string values.

    Scan char by char tracking string state. While inside a string, a `"` is
    treated as the real closing quote only if the next non-space char is one of
    , } ] :  or end-of-input. Any other `"` is content and gets escaped.
    """
    out: list[str] = []
    in_str = False
    i, n = 0, len(s)
    while i < n:
        c = s[i]
        if not in_str:
            out.append(c)
            if c == '"':
                in_str = True
            i += 1
            continue
        # inside a string
        if c == "\\":  # keep existing escapes intact (\" \\ \n ...)
            out.append(c)
            if i + 1 < n:
                out.append(s[i + 1])
                i += 2
            else:
                i += 1
            continue
        if c == '"':
            j = i + 1
            while j < n and s[j] in " \t\r\n":
                j += 1
            if j >= n or s[j] in ",}]:":
                out.append('"')      # genuine closing quote
                in_str = False
            else:
                out.append('\\"')    # stray inner quote -> escape it
            i += 1
            continue
        out.append(c)
        i += 1
    return "".join(out)


def extract_json(raw: str) -> dict[str, Any]:
    """Best-effort parse of a JSON object from a model response.

    Raises ValueError if no strategy yields a dict.
    """
    if raw is None:
        raise ValueError("empty model response")

    # 1) straight parse
    try:
        obj = json.loads(raw)
        if isinstance(obj, dict):
            return obj
    except json.JSONDecodeError:
        pass

    region = _candidate_region(raw)

    # 2) parse the isolated region
    for attempt in (region, _strip_trailing_commas(region)):
        try:
            obj = json.loads(attempt)
            if isinstance(obj, dict):
                return obj
        except json.JSONDecodeError:
            continue

    # 3) repair unescaped inner quotes, then retry (+ trailing-comma strip)
    repaired = _escape_inner_quotes(region)
    for attempt in (repaired, _strip_trailing_commas(repaired)):
        try:
            obj = json.loads(attempt)
            if isinstance(obj, dict):
                return obj
        except json.JSONDecodeError:
            continue

    raise ValueError(f"could not parse JSON from model response: {raw[:200]!r}")
