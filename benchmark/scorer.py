"""Deterministic scorer for benchmark tasks. No LLM calls.

score_output(task, output) applies every check in task["checks"] to the model output.

Check types (see contract 2.4):
  json_valid    output parses as JSON (after stripping a markdown code fence).
  json_keys     parsed object has EXACTLY the keys in "value" (no missing, no extra, any order).
  one_of        the value is exactly one of the strings in "value" (case-sensitive).
  max_words     at most "value" whitespace-separated words.
  min_words     at least "value" words.
  starts_with   the text starts with "value" (leading whitespace is ignored).
  contains      "value" appears in the text (case-insensitive unless "case_sensitive": true).
  not_contains  "value" does not appear (same options). "whole_word": true matches whole words only.
  regex         re.search(value, text, re.MULTILINE) finds a match.
  order         every string in the list "value" appears, in that order.

If a check has "path" (dot notation, list indices are numbers, e.g. "items.0.name") it applies to
that field of the parsed JSON. If the output is not valid JSON, or the path is missing, the check
fails with a clear reason. A non-string field is turned into text with json.dumps before text checks.
Without "path", text checks apply to the whole output (fence stripped); json_keys applies to the
top-level object.
"""
from __future__ import annotations

import json
import re

_FENCE_RE = re.compile(r"\A```[A-Za-z0-9_-]*[ \t]*\r?\n(.*?)\r?\n?```\Z", re.DOTALL)
_MISSING = object()


def strip_fences(output: str) -> str:
    """Trim the output and remove one wrapping ``` fence, if the whole output is fenced."""
    text = (output or "").strip()
    match = _FENCE_RE.match(text)
    return match.group(1).strip() if match else text


def parse_json(text: str):
    """Return (ok, value). `text` should already be fence-stripped."""
    try:
        return True, json.loads(text)
    except (ValueError, TypeError):
        return False, None


def resolve_path(data, path: str):
    """Follow a dot path through dicts and lists. Returns _MISSING if it does not exist."""
    cur = data
    for part in path.split("."):
        if isinstance(cur, dict) and part in cur:
            cur = cur[part]
        elif isinstance(cur, list) and part.isdigit() and int(part) < len(cur):
            cur = cur[int(part)]
        else:
            return _MISSING
    return cur


def as_text(value) -> str:
    return value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)


def word_count(text: str) -> int:
    return len(text.split())


class _Ctx:
    """The output as the checks see it: fence-stripped text plus lazily parsed JSON."""

    def __init__(self, output: str) -> None:
        self.text = strip_fences(output)
        self.json_ok, self.json = parse_json(self.text)

    def target(self, check: dict):
        """Return (value, error). With a path the value is a field of the parsed JSON."""
        path = check.get("path")
        if not path:
            return self.text, None
        if not self.json_ok:
            return None, f"output is not valid JSON, cannot read '{path}'"
        value = resolve_path(self.json, path)
        if value is _MISSING:
            return None, f"path '{path}' not found in the JSON"
        return value, None


def _find(needle: str, haystack: str, check: dict) -> bool:
    flags = 0 if check.get("case_sensitive") else re.IGNORECASE
    pattern = re.escape(needle)
    if check.get("whole_word"):
        pattern = rf"(?<!\w){pattern}(?!\w)"
    return re.search(pattern, haystack, flags) is not None


def _check_json_valid(check, ctx):
    return (True, "ok") if ctx.json_ok else (False, "output is not valid JSON")


def _check_json_keys(check, ctx):
    value, err = ctx.target(check)
    if err:
        return False, err
    if not check.get("path"):
        if not ctx.json_ok:
            return False, "output is not valid JSON, cannot read keys"
        value = ctx.json
    if not isinstance(value, dict):
        return False, "value is not a JSON object"
    want, have = set(check["value"]), set(value)
    missing, extra = sorted(want - have), sorted(have - want)
    if missing or extra:
        parts = ([f"missing keys {missing}"] if missing else []) + ([f"extra keys {extra}"] if extra else [])
        return False, "; ".join(parts)
    return True, "ok"


def _check_one_of(check, ctx):
    value, err = ctx.target(check)
    if err:
        return False, err
    shown = value.strip() if isinstance(value, str) else value
    if shown in check["value"]:
        return True, "ok"
    return False, f"{as_text(value)[:60]!r} is not one of {check['value']}"


def _check_words(check, ctx, longer: bool):
    value, err = ctx.target(check)
    if err:
        return False, err
    n, limit = word_count(as_text(value)), check["value"]
    if longer:  # max_words
        return (True, "ok") if n <= limit else (False, f"{n} words; the limit is {limit}")
    return (True, "ok") if n >= limit else (False, f"{n} words; the minimum is {limit}")


def _check_starts_with(check, ctx):
    value, err = ctx.target(check)
    if err:
        return False, err
    text = as_text(value).lstrip()
    if text.startswith(check["value"]):
        return True, "ok"
    return False, f"starts with {text[:30]!r}, expected {check['value']!r}"


def _check_contains(check, ctx):
    value, err = ctx.target(check)
    if err:
        return False, err
    if _find(check["value"], as_text(value), check):
        return True, "ok"
    return False, f"{check['value']!r} not found"


def _check_not_contains(check, ctx):
    value, err = ctx.target(check)
    if err:
        return False, err
    if _find(check["value"], as_text(value), check):
        return False, f"forbidden text {check['value']!r} is present"
    return True, "ok"


def _check_regex(check, ctx):
    value, err = ctx.target(check)
    if err:
        return False, err
    if re.search(check["value"], as_text(value), re.MULTILINE):
        return True, "ok"
    return False, f"pattern {check['value']!r} did not match"


def _check_order(check, ctx):
    value, err = ctx.target(check)
    if err:
        return False, err
    text, pos = as_text(value), 0
    for item in check["value"]:
        idx = text.find(item, pos)
        if idx < 0:
            return False, f"{item!r} missing or out of order"
        pos = idx + len(item)
    return True, "ok"


CHECKS = {
    "json_valid": _check_json_valid,
    "json_keys": _check_json_keys,
    "one_of": _check_one_of,
    "max_words": lambda c, x: _check_words(c, x, longer=True),
    "min_words": lambda c, x: _check_words(c, x, longer=False),
    "starts_with": _check_starts_with,
    "contains": _check_contains,
    "not_contains": _check_not_contains,
    "regex": _check_regex,
    "order": _check_order,
}


def run_check(check: dict, ctx: _Ctx) -> tuple[bool, str]:
    """Run one check. A malformed check or bad regex fails with a reason instead of raising."""
    fn = CHECKS.get(check.get("type"))
    if fn is None:
        return False, f"unknown check type {check.get('type')!r}"
    try:
        return fn(check, ctx)
    except (KeyError, TypeError, re.error) as exc:
        return False, f"bad check definition: {exc!r}"


def score_output(task: dict, output: str) -> dict:
    """Score one output against task["checks"].

    Returns {"passed": bool, "failed_checks": [ids], "failure_label": label of the FIRST
    failed check or None, "details": {check id: "ok" or short reason}}.
    """
    ctx = _Ctx(output)
    failed: list[str] = []
    details: dict[str, str] = {}
    label = None
    for check in task["checks"]:
        ok, reason = run_check(check, ctx)
        details[check["id"]] = reason
        if not ok:
            failed.append(check["id"])
            if label is None:
                label = check.get("label") or "other"
    return {"passed": not failed, "failed_checks": failed, "failure_label": label, "details": details}
