"""Skill Doctor, server side (registered by web/server.py). Paste a skill, see how risky it is for a small model, the steps the
harness would make, a suggested rewrite, and (only if you add simple checks) a plain-vs-harness try.

  POST /doctor/compile  {skill_text}                       -> the steps the splitter produces (1 to 2 model calls)
  POST /doctor/rewrite  {skill_text}                       -> a rewrite, lint before and after, constraints the rewrite lost (1 call)
  POST /doctor/try      {skill_text, input, checks}        -> plain and harness scored by YOUR checks (about 15 model calls)

The lint score comes from the existing POST /lint route (no model). Anything not scored by checks is labelled unverified.
One model request at a time: a second one gets HTTP 429 instead of competing for the free-tier rate limit.
"""
from __future__ import annotations

import sys
import threading
from pathlib import Path

from flask import Blueprint, jsonify, request

WEB = Path(__file__).resolve().parent
ROOT = WEB.parent
sys.path.insert(0, str(ROOT))

MAX_SKILL = 6000
MAX_INPUT = 1500
MAX_STEPS = 6

try:
    from tools.lint_skill import lint as _lint
except ImportError:  # pragma: no cover
    _lint = None
try:
    from skillcompiler import compile_skill as _compile, llm as _llm, run_skill as _run_skill
except ImportError:  # pragma: no cover
    _compile = _llm = _run_skill = None
try:
    from benchmark import autorewrite as _autorewrite
except ImportError:  # pragma: no cover
    _autorewrite = None
try:
    from benchmark.run_plain import run_plain as _run_plain
    from benchmark.scorer import score_output as _score
except ImportError:  # pragma: no cover
    _run_plain = _score = None

bp = Blueprint("doctor", __name__, url_prefix="/doctor")
BUSY = threading.Lock()


class BadRequest(ValueError):
    pass


def read_skill(body: object) -> str:
    if not isinstance(body, dict) or not isinstance(body.get("skill_text"), str) or not body["skill_text"].strip():
        raise BadRequest("skill_text is required")
    skill = body["skill_text"]
    if len(skill) > MAX_SKILL:
        raise BadRequest(f"The skill is {len(skill)} characters; the limit is {MAX_SKILL}.")
    return skill


def build_checks(spec: object) -> list[dict]:
    """Simple user checks -> scorer checks. Supported: max_words, starts_with, contains, json_keys. Empty -> no checks."""
    if not isinstance(spec, dict):
        return []
    checks: list[dict] = []

    def add(kind: str, label: str, **extra) -> None:
        checks.append({"id": f"u{len(checks) + 1}", "type": kind, "label": label, **extra})

    words = spec.get("max_words")
    if words not in (None, "", 0):
        try:
            limit = int(words)
        except (TypeError, ValueError):
            raise BadRequest("max_words must be a whole number") from None
        if not 1 <= limit <= 2000:
            raise BadRequest("max_words must be between 1 and 2000")
        add("max_words", "ignored_constraint", value=limit)
    for key, kind in (("starts_with", "starts_with"), ("contains", "contains")):
        value = spec.get(key)
        if isinstance(value, str) and value.strip():
            if len(value) > 200:
                raise BadRequest(f"{key} is too long")
            add(kind, "ignored_constraint", value=value)
    keys = spec.get("json_keys")
    if isinstance(keys, str):
        keys = [k.strip() for k in keys.split(",")]
    if isinstance(keys, list):
        keys = [k for k in keys if isinstance(k, str) and k.strip()]
        if keys:
            add("json_valid", "wrong_format")
            add("json_keys", "skipped_step", value=keys[:20])
    return checks


def describe(check: dict) -> str:
    kind, value = check["type"], check.get("value")
    if kind == "max_words":
        return f"at most {value} words"
    if kind == "starts_with":
        return f'starts with "{value}"'
    if kind == "contains":
        return f'contains "{value}"'
    if kind == "json_keys":
        return f"has the JSON keys {', '.join(value or [])}"
    if kind == "json_valid":
        return "is valid JSON"
    return kind


def score_side(checks: list[dict], output: str) -> dict:
    result = _score({"checks": checks}, output)
    labels = {c["id"]: describe(c) for c in checks}
    failed = [{"id": cid, "check": labels.get(cid, cid), "reason": result.get("details", {}).get(cid, "")} for cid in result["failed_checks"]]
    return {"output": output, "passed": bool(result["passed"]), "failed": failed}


def _guard(handler):
    """Shared handling: bad input -> 400, busy -> 429, a missing piece -> 501, a model/API error -> 502."""
    def wrapped():
        try:
            body = request.get_json(silent=True)
            skill = read_skill(body)
            if not BUSY.acquire(blocking=False):
                return jsonify(error="Another request is using the model right now. Try again in a minute."), 429
            try:
                return jsonify(handler(skill, body))
            finally:
                BUSY.release()
        except BadRequest as exc:
            return jsonify(error=str(exc)), 400
        except NotImplementedError as exc:
            return jsonify(error=str(exc)), 501
        except Exception as exc:  # noqa: BLE001 - tell the page, do not crash the server
            return jsonify(error=f"{type(exc).__name__}: {exc}"), 502
    wrapped.__name__ = handler.__name__
    return wrapped


def do_compile(skill: str, body: dict) -> dict:
    if _compile is None:
        raise NotImplementedError("The harness is not importable here.")
    plan = _compile(skill)
    return {"unverified": True, "skill": plan.get("skill_name"), "warnings": plan.get("warnings", []),
            "steps": [{"id": s["id"], "title": s["title"], "instruction": s["instruction"], "output_format": s["output_format"]} for s in plan["steps"]],
            "note": "A model split this skill, so the steps can differ from run to run. Nothing here is scored."}


def do_rewrite(skill: str, body: dict) -> dict:
    if _autorewrite is None or _llm is None or _lint is None:
        raise NotImplementedError("The rewrite needs benchmark/autorewrite.py and the harness.")
    rewritten = _autorewrite.clean_rewrite(_llm.call_llm(_autorewrite.PROMPT.format(skill_text=skill)))
    lost = _autorewrite.lost_constraints(skill, rewritten)
    return {"unverified": True, "rewritten": rewritten, "lint_before": _lint(skill), "lint_after": _lint(rewritten), "lost": lost,
            "note": ("The rewrite dropped these numbers or quoted phrases: " + "; ".join(lost) + ". Do not trust it without fixing that." if lost
                     else "No number or quoted phrase was lost. The lint score is a risk estimate, not a measured pass rate.")}


def do_try(skill: str, body: dict) -> dict:
    if _run_plain is None or _run_skill is None or _score is None:
        raise NotImplementedError("Trying a skill needs the harness, benchmark.run_plain and benchmark.scorer.")
    user_input = body.get("input")
    if not isinstance(user_input, str) or not user_input.strip():
        raise BadRequest("The example input is empty.")
    if len(user_input) > MAX_INPUT:
        raise BadRequest(f"The input is {len(user_input)} characters; the limit is {MAX_INPUT}.")
    checks = build_checks(body.get("checks"))
    if not checks:
        raise BadRequest("Add at least one check (max words, starts with, contains, or JSON keys). Without checks nothing can be scored.")
    plain = score_side(checks, str(_run_plain(skill, user_input).get("final_output", "")))
    trace = _run_skill(skill, user_input, mode="adaptive")
    harness = score_side(checks, trace["final_output"])
    harness["model_calls"] = trace["totals"]["llm_calls"]
    return {"checks": [describe(c) for c in checks], "plain": plain, "harness": harness, "one_run": True,
            "note": "Scored only by the checks you added, on one run each. Gemma's output changes from run to run."}


bp.add_url_rule("/compile", "compile", _guard(do_compile), methods=["POST"])
bp.add_url_rule("/rewrite", "rewrite", _guard(do_rewrite), methods=["POST"])
bp.add_url_rule("/try", "try_it", _guard(do_try), methods=["POST"])
