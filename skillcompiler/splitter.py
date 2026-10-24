"""Split a SKILL.md into an ordered plan (plan.json shape)."""
from __future__ import annotations

import json
import re

from . import llm

SPLITTER_PROMPT = """You are a precise parser. Break the agent skill below into the smallest ordered
list of steps that a small language model could do one at a time.
Return ONLY valid JSON in this shape:
{{"steps":[{{"id":1,"title":"...","instruction":"...",
  "output_format":"text|json|list|number|one_of:a|b|c|max_words:N",
  "expected_output":"...","depends_on":[]}}]}}
Rules:
- Keep every requirement from the skill. Do not add steps the skill does not have.
- One action per step.
- Copy constraints (word limits, allowed values, required phrases) into the step they apply to.
- The last step must produce the final answer in the format the skill requires.
- If a rule applies to the final answer (word limit, required start or end, forbidden words), repeat that rule in the last step's instruction.
SKILL:
{skill_text}
"""

FORMAT_RE = re.compile(r"^(text|json|list|number|one_of:[^|]+(\|[^|]+)*|max_words:\d+)$")
NUMBERED_RE = re.compile(r"^\s*(\d+)[.)]\s+(.*\S)\s*$")
HEADING_RE = re.compile(r"^\s{0,3}#{2,6}\s+(.*\S)\s*$")


def _strip_fences(text: str) -> str:
    """Remove ```json fences models like to add."""
    text = text.strip()
    match = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    return match.group(1).strip() if match else text


def _parse_frontmatter(skill_text: str) -> tuple[dict, str]:
    """Return (frontmatter fields, body). Handles simple `key: value` lines."""
    match = re.match(r"^---\s*\n(.*?)\n---\s*\n?", skill_text, re.DOTALL)
    if not match:
        return {}, skill_text
    fields = {}
    for line in match.group(1).splitlines():
        if ":" in line:
            key, _, value = line.partition(":")
            fields[key.strip()] = value.strip().strip("\"'")
    return fields, skill_text[match.end():]


def validate_steps(steps: list) -> list[dict]:
    """Check a step list against the contract; raise ValueError if invalid."""
    if not isinstance(steps, list) or not steps:
        raise ValueError("steps must be a non-empty list")
    seen: set[int] = set()
    cleaned = []
    for step in steps:
        if not isinstance(step, dict):
            raise ValueError("each step must be an object")
        sid = step.get("id")
        if not isinstance(sid, int) or sid in seen:
            raise ValueError(f"bad or duplicate step id: {sid!r}")
        instruction = str(step.get("instruction", "")).strip()
        if not instruction:
            raise ValueError(f"step {sid} has an empty instruction")
        depends = step.get("depends_on", [])
        if not isinstance(depends, list) or any(d not in seen for d in depends):
            raise ValueError(f"step {sid} depends on a step that is not earlier")
        fmt = str(step.get("output_format", "text")).strip()
        if not FORMAT_RE.match(fmt):
            fmt = "text"
        cleaned.append({
            "id": sid,
            "title": str(step.get("title") or instruction[:40]).strip(),
            "instruction": instruction,
            "output_format": fmt,
            "expected_output": str(step.get("expected_output", "")).strip(),
            "depends_on": depends,
        })
        seen.add(sid)
    return cleaned


def rule_based_steps(body: str) -> list[dict]:
    """Fallback: numbered list, then headings, then paragraphs."""
    lines = body.splitlines()
    chunks: list[tuple[str, str]] = []  # (title, instruction)

    numbered = [(i, NUMBERED_RE.match(l)) for i, l in enumerate(lines)]
    numbered = [(i, m) for i, m in numbered if m]
    if numbered:
        for n, (i, m) in enumerate(numbered):
            end = numbered[n + 1][0] if n + 1 < len(numbered) else len(lines)
            extra = " ".join(l.strip() for l in lines[i + 1:end] if l.strip())
            text = f"{m.group(2)} {extra}".strip()
            chunks.append((m.group(2)[:60], text))
    else:
        heads = [(i, HEADING_RE.match(l)) for i, l in enumerate(lines)]
        heads = [(i, m) for i, m in heads if m]
        if heads:
            for n, (i, m) in enumerate(heads):
                end = heads[n + 1][0] if n + 1 < len(heads) else len(lines)
                text = " ".join(l.strip() for l in lines[i + 1:end] if l.strip())
                chunks.append((m.group(1), f"{m.group(1)}. {text}".strip()))
        else:
            paras = [p.strip() for p in re.split(r"\n\s*\n", body) if p.strip()]
            chunks = [(p[:60], p.replace("\n", " ")) for p in paras]

    steps = []
    for n, (title, text) in enumerate(chunks, start=1):
        steps.append({
            "id": n,
            "title": title,
            "instruction": text,
            "output_format": "text",
            "expected_output": "",
            "depends_on": [n - 1] if n > 1 else [],
        })
    return validate_steps(steps)


LEADING_MARK_RE = re.compile(r"^\s*(?:\d+[.)]|[-*])\s+")
QUOTED_RE = re.compile(r"[\"“]([^\"”]{2,60})[\"”]")
NUMBER_RE = re.compile(r"(?<![\w.])\d+(?:\.\d+)?(?![\w])")

RESPLIT_NOTE = """
Your previous plan left out these items from the skill: {missing}
Return the full plan again and include each item, exactly as written, in the step it belongs to.
"""


def requirement_tokens(body: str) -> list[str]:
    """Numbers and quoted phrases in the skill text (limits, allowed values, required wording).
    List numbering such as '3.' at the start of a line is ignored."""
    found: list[str] = []
    for line in body.splitlines():
        line = LEADING_MARK_RE.sub("", line)
        found += QUOTED_RE.findall(line) + NUMBER_RE.findall(QUOTED_RE.sub("", line))
    return list(dict.fromkeys(f.strip() for f in found if f.strip()))


def missing_requirements(body: str, steps: list[dict]) -> list[str]:
    """Requirement tokens from the skill that appear nowhere in the plan."""
    haystack = " ".join(
        f"{s['title']} {s['instruction']} {s['expected_output']} {s['output_format']}"
        for s in steps).lower()
    missing = []
    for token in requirement_tokens(body):
        if re.fullmatch(r"\d+(?:\.\d+)?", token):
            if not re.search(r"(?<![\d.])" + re.escape(token) + r"(?!\d)", haystack):
                missing.append(token)
        elif token.lower() not in haystack:
            missing.append(f'"{token}"')
    return missing


def _model_steps(body: str, model: str | None, extra: str = "") -> list[dict]:
    """Ask the model for a plan; retry once on bad JSON."""
    prompt = SPLITTER_PROMPT.format(skill_text=body) + extra
    last: Exception | None = None
    for _ in range(2):
        raw = llm.call_llm(prompt, model=model)
        try:
            return validate_steps(json.loads(_strip_fences(raw)).get("steps"))
        except (ValueError, AttributeError, TypeError) as exc:
            last = exc  # json.JSONDecodeError is a ValueError
    raise ValueError(f"model returned an invalid plan: {last}")


def compile_skill(skill_text: str, model: str | None = None,
                  source_file: str = "") -> dict:
    """SKILL.md text -> plan.json dict. Model first, rule-based fallback."""
    fields, body = _parse_frontmatter(skill_text)
    warnings: list[str] = []
    try:
        steps = _model_steps(body, model)
        missing = missing_requirements(body, steps)
        if missing:  # the model dropped a limit or a required phrase: ask once more
            note = RESPLIT_NOTE.format(missing=", ".join(missing))
            try:
                steps = _model_steps(body, model, extra=note)
            except (ValueError, RuntimeError):
                pass  # keep the first plan
            missing = missing_requirements(body, steps)
        if missing:
            warnings.append("The plan does not mention these items from the skill: "
                            + ", ".join(missing))
    except (ValueError, RuntimeError):
        steps = rule_based_steps(body)  # copies the skill text, so nothing is dropped
    plan = {
        "skill_name": fields.get("name", "skill"),
        "source_file": source_file,
        "steps": steps,
    }
    if warnings:
        plan["warnings"] = warnings  # optional contract field
    return plan
