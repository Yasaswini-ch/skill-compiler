"""Run a skill step by step: prompt, check, retry with feedback, write a trace."""
from __future__ import annotations

import os
import time
import uuid

from . import llm
from .checker import check_step
from .splitter import compile_skill

STEP_PROMPT = """You are completing ONE step of a larger task. Do only this step.

Step {id}: {title}
Instruction: {instruction}
Required output: {expected_output}
Answer format: {format_hint}

Original input:
{user_input}
{earlier}
Reply with only the output for this step. No explanation, no extra text.
"""

RETRY_NOTE = """
Your previous answer was rejected.
Previous answer: {previous}
Problem: {note}
Fix the problem and answer again.
"""


def format_hint(output_format: str) -> str:
    """Plain-words description of an output_format, so the model does not copy the label."""
    fmt = output_format or "text"
    if fmt.startswith("one_of:"):
        options = ", ".join(o for o in fmt[len("one_of:"):].split("|") if o)
        return f"exactly one of these values and nothing else: {options}"
    if fmt.startswith("max_words:"):
        return f"at most {fmt[len('max_words:'):]} words"
    return {
        "text": "plain text",
        "json": "valid JSON only",
        "list": "a list, one item per line",
        "number": "a single number and nothing else",
    }.get(fmt, fmt)


def _earlier_block(step: dict, outputs: dict[int, str], titles: dict[int, str]) -> str:
    """Text listing the outputs of the steps this step depends on."""
    lines = [f"Step {d} ({titles[d]}): {outputs[d]}" for d in step["depends_on"]
             if d in outputs]
    return ("\nResults of earlier steps:\n" + "\n".join(lines) + "\n") if lines else ""


def build_prompt(step: dict, user_input: str, earlier: str,
                 previous: str = "", note: str = "") -> str:
    """Prompt for one step, with checker feedback appended on a retry."""
    prompt = STEP_PROMPT.format(
        id=step["id"], title=step["title"], instruction=step["instruction"],
        expected_output=step.get("expected_output") or "as the instruction says",
        format_hint=format_hint(step.get("output_format", "text")),
        user_input=user_input, earlier=earlier,
    )
    if previous:
        prompt += RETRY_NOTE.format(previous=previous, note=note)
    return prompt


def _run_step(step: dict, user_input: str, outputs: dict[int, str],
              titles: dict[int, str], model: str | None, max_retries: int,
              verify: bool) -> tuple[dict, str]:
    """Run one step with retries. Returns (trace entry, last output)."""
    earlier = _earlier_block(step, outputs, titles)
    context = f"{user_input}\n{earlier}".strip()
    attempts: list[dict] = []
    output, note = "", ""
    ok = False
    for n in range(max_retries + 1):
        start = time.time()
        prompt = build_prompt(step, user_input, earlier, output if n else "", note)
        try:
            output = llm.call_llm(prompt, model=model).strip()
            format_ok, verified, note = check_step(step, output, context, model, verify)
        except RuntimeError as exc:  # API gave up: record it and carry on
            output, format_ok, verified, note = "", False, False, f"LLM call failed: {exc}"
        attempts.append({
            "output": output, "format_ok": format_ok, "verified": verified,
            "checker_note": note, "latency_ms": int((time.time() - start) * 1000),
        })
        ok = format_ok and verified
        if ok:
            break
    status = "fail" if not ok else ("pass" if len(attempts) == 1 else "repaired")
    entry = {"step_id": step["id"], "title": step["title"], "status": status,
             "attempts": attempts}
    return entry, output


def run_skill(skill_text: str, user_input: str, model: str | None = None,
              max_retries: int = 2, verify: bool = True,
              plan: dict | None = None) -> dict:
    """Split (unless a plan is given), run every step, return a trace.json dict."""
    llm.stats.reset()
    plan = plan or compile_skill(skill_text, model)
    outputs: dict[int, str] = {}
    titles = {s["id"]: s["title"] for s in plan["steps"]}
    trace_steps = []
    for step in plan["steps"]:
        entry, output = _run_step(step, user_input, outputs, titles, model,
                                  max_retries, verify)
        trace_steps.append(entry)
        outputs[step["id"]] = output
    retries = sum(len(s["attempts"]) - 1 for s in trace_steps)
    return {
        "run_id": "r-" + uuid.uuid4().hex[:8],
        "mode": "harness",
        "mock": False,
        "model": model or os.environ.get("GEMMA_MODEL", ""),
        "skill": plan.get("skill_name", "skill"),
        "input": user_input,
        "steps": trace_steps,
        "final_output": outputs[plan["steps"][-1]["id"]] if plan["steps"] else "",
        "totals": {"llm_calls": llm.stats.calls, "latency_ms": llm.stats.latency_ms,
                   "retries": retries},
    }
