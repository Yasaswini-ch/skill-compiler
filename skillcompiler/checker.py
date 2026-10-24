"""Check one step's output: programmatic format check, then a PASS/FAIL model call."""
from __future__ import annotations

import json
import re

from . import llm

VERIFIER_PROMPT = """Instruction given to an assistant:
{instruction}
Required output: {expected_output}
{context_block}Assistant's output:
{output}
Does the output follow the instruction? Answer FAIL only if the output clearly breaks
the instruction or a stated rule. If more than one answer is reasonable, answer PASS.
Reply on ONE line, 25 words at most:
PASS or FAIL: <short reason>
"""

VERDICT_RE = re.compile(r"^\W*(PASS|FAIL)\b[\s:.\-*]*(.*)$", re.IGNORECASE)
QUOTE = "\"“”"
BEGIN_RE = re.compile(
    r"(?:begin|start)s?\s+with\s+(?:the\s+(?:phrase|text|word)\s+)?[\"“](.+?)[\"”]",
    re.IGNORECASE)
FORBID_RE = re.compile(
    r"(?:must\s+not|never|do\s+not|don't)\s+(?:contain|use|include)\s+"
    r"(?:the\s+)?(?:word\s+|phrase\s+)?[\"“](.+?)[\"”]", re.IGNORECASE)
LIST_ITEM_RE = re.compile(r"^\s*(?:[-*•]|\d+[.)])\s+\S")


def _strip_fences(text: str) -> str:
    """Remove ```json fences models like to add."""
    match = re.search(r"```(?:\w+)?\s*(.*?)```", text, re.DOTALL)
    return match.group(1).strip() if match else text.strip()


def _normalize(text: str) -> str:
    """Lowercase and drop surrounding quotes, punctuation and whitespace."""
    return text.strip().strip("\"'`*.!, \n\t").lower()


def check_format(output_format: str, output: str) -> tuple[bool, str]:
    """Programmatic format check. Returns (ok, note)."""
    text = output.strip()
    if not text:
        return False, "Output is empty"
    fmt = output_format or "text"

    if fmt == "text":
        return True, "ok"

    if fmt == "json":
        try:
            json.loads(_strip_fences(text))
        except ValueError as exc:
            return False, f"Output is not valid JSON ({exc})"
        return True, "ok"

    if fmt == "list":
        lines = [l for l in text.splitlines() if l.strip()]
        if any(LIST_ITEM_RE.match(l) for l in lines) or len(lines) >= 2:
            return True, "ok"
        if len([i for i in re.split(r"[,;]", text) if i.strip()]) >= 2:
            return True, "ok"  # comma-separated list on one line
        try:
            if isinstance(json.loads(_strip_fences(text)), list):
                return True, "ok"
        except ValueError:
            pass
        return False, "Expected a list with more than one item"

    if fmt == "number":
        try:
            float(text.rstrip(".").replace(",", ""))
        except ValueError:
            return False, "Expected a single number and nothing else"
        return True, "ok"

    if fmt.startswith("one_of:"):
        options = [o.strip() for o in fmt[len("one_of:"):].split("|") if o.strip()]
        if _normalize(text) in [o.lower() for o in options]:
            return True, "ok"
        return False, f"Expected exactly one of: {', '.join(options)}"

    if fmt.startswith("max_words:"):
        limit = int(fmt[len("max_words:"):])
        words = len(text.split())
        if words <= limit:
            return True, "ok"
        return False, f"Output has {words} words; the limit is {limit}"

    return True, "ok"  # unknown format: do not block the run


def check_constraints(instruction: str, output_format: str, output: str) -> tuple[bool, str]:
    """Enforce 'must begin with "X"' and 'must not contain the word "Y"' rules in the
    instruction without a model call. A <placeholder> inside X matches any text."""
    text = output.strip()
    if (output_format or "text").startswith("json"):
        return True, "ok"  # JSON starts with "{"; its wording rules belong to the verifier
    for phrase in BEGIN_RE.findall(instruction):
        pieces = re.split(r"<[^>]+>", phrase)
        pattern = ".+?".join(re.escape(p) for p in pieces)
        if not re.match(pattern, text.lstrip(QUOTE + "`*_ \n")):
            return False, f'Output must begin with "{phrase}"'
    for phrase in FORBID_RE.findall(instruction):
        if re.search(r"\b" + re.escape(phrase) + r"\b", text, re.IGNORECASE):
            return False, f'Output must not contain "{phrase}"'
    return True, "ok"


def parse_verdict(reply: str) -> tuple[bool | None, str]:
    """Find the PASS/FAIL line in a verifier reply. None if there isn't one."""
    for line in reply.splitlines():
        match = VERDICT_RE.match(line.strip())
        if match:
            passed = match.group(1).upper() == "PASS"
            reason = match.group(2).strip()
            if len(reason) > 200:
                reason = reason[:200].rstrip() + "..."
            return passed, reason or ("ok" if passed else "Verifier said FAIL")
    return None, ""


def verify_output(step: dict, output: str, context: str = "",
                  model: str | None = None) -> tuple[bool, str]:
    """Second model call: does the output follow the instruction? (verified, note)."""
    block = f"Information the assistant was given:\n{context}\n" if context else ""
    prompt = VERIFIER_PROMPT.format(
        instruction=step.get("instruction", ""),
        expected_output=step.get("expected_output", "") or "as the instruction says",
        context_block=block,
        output=output,
    )
    try:
        reply = llm.call_llm(prompt, model=model)
    except RuntimeError as exc:
        return True, f"verifier unavailable, accepted ({exc})"
    passed, reason = parse_verdict(reply)
    if passed is None:
        return True, "verifier reply unclear, accepted"
    return passed, reason


def check_step(step: dict, output: str, context: str = "", model: str | None = None,
               verify: bool = True) -> tuple[bool, bool, str]:
    """Return (format_ok, verified, note). Verification is skipped if the format fails."""
    fmt = step.get("output_format", "text")
    format_ok, note = check_format(fmt, output)
    if format_ok:
        format_ok, note = check_constraints(step.get("instruction", ""), fmt, output)
    if not format_ok:
        return False, False, note
    if not verify:
        return True, True, "ok (format only)"
    verified, note = verify_output(step, output, context, model)
    return True, verified, note
