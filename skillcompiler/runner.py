"""Run a skill step by step: prompt, check, retry with feedback, write a trace."""
from __future__ import annotations

import os
import time
import uuid
from collections.abc import Callable

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
        "list": "a list, laid out as the instruction says",
        "number": "a single number and nothing else",
    }.get(fmt, fmt)


def _emit(on_event: Callable[[dict], None] | None, event: dict) -> None:
    """Report progress to the caller. A broken callback must never break a run."""
    if on_event is None:
        return
    try:
        on_event(event)
    except Exception:  # noqa: BLE001 - the run matters more than the listener
        pass


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
              verify: bool, on_event: Callable[[dict], None] | None = None
              ) -> tuple[dict, str]:
    """Run one step with retries. Returns (trace entry, last output)."""
    _emit(on_event, {"type": "step_start", "step_id": step["id"], "title": step["title"]})
    earlier = _earlier_block(step, outputs, titles)
    context = f"{user_input}\n{earlier}".strip()
    attempts: list[dict] = []
    output, note = "", ""
    ok = False
    for n in range(max_retries + 1):
        _emit(on_event, {"type": "attempt_start", "step_id": step["id"], "attempt": n + 1})
        start = time.time()
        prompt = build_prompt(step, user_input, earlier, output if n else "", note)
        try:
            output = llm.call_llm(prompt, model=model).strip()
            format_ok, verified, note = check_step(step, output, context, model, verify)
        except RuntimeError as exc:  # API gave up: record it and carry on
            output, format_ok, verified, note = "", False, False, f"LLM call failed: {exc}"
        if (format_ok and not verified
                and any(a["format_ok"] and a["output"] == output for a in attempts)):
            # The model gave this exact answer before, and only the model verifier
            # objects. Its judgement is inconsistent (it rejected a correct sum, and
            # flip-flopped on an ambiguous label), so keep the model's answer.
            verified = True
            note = f"model repeated its answer; verifier objection overruled ({note[:120]})"
        attempts.append({
            "output": output, "format_ok": format_ok, "verified": verified,
            "checker_note": note, "latency_ms": int((time.time() - start) * 1000),
        })
        ok = format_ok and verified
        _emit(on_event, {"type": "attempt_end", "step_id": step["id"], "attempt": n + 1,
                         "ok": ok, **attempts[-1]})
        if ok:
            break
    status = "fail" if not ok else ("pass" if len(attempts) == 1 else "repaired")
    entry = {"step_id": step["id"], "title": step["title"], "status": status,
             "attempts": attempts}
    _emit(on_event, {"type": "step_end", "step_id": step["id"], "status": status})
    return entry, output


def run_skill(skill_text: str, user_input: str, model: str | None = None,
              max_retries: int = 2, verify: bool | None = None,
              plan: dict | None = None,
              on_event: Callable[[dict], None] | None = None) -> dict:
    """Split (unless a plan is given), run every step, return a trace.json dict.

    on_event, if given, is called with a plain dict as the run progresses, so a UI can show
    steps as they finish: run_start, plan, step_start, attempt_start, attempt_end, step_end,
    run_end (carrying the full trace). It is called from the running thread and an
    exception raised inside it is ignored.
    """
    if verify is None:  # SKILLCOMPILER_VERIFY=0 switches the verifier call off globally
        verify = os.environ.get("SKILLCOMPILER_VERIFY", "1") != "0"
    llm.stats.reset()
    _emit(on_event, {"type": "run_start", "will_split": plan is None})
    plan = plan or compile_skill(skill_text, model)
    _emit(on_event, {"type": "plan", "skill": plan.get("skill_name", "skill"),
                     "steps": [{"id": st["id"], "title": st["title"]} for st in plan["steps"]],
                     "warnings": plan.get("warnings", [])})
    outputs: dict[int, str] = {}
    titles = {s["id"]: s["title"] for s in plan["steps"]}
    trace_steps = []
    for step in plan["steps"]:
        entry, output = _run_step(step, user_input, outputs, titles, model,
                                  max_retries, verify, on_event)
        trace_steps.append(entry)
        outputs[step["id"]] = output
    retries = sum(len(s["attempts"]) - 1 for s in trace_steps)
    trace = {
        "run_id": "r-" + uuid.uuid4().hex[:8],
        "mode": "harness",
        "mock": False,
        "model": model or os.environ.get("GEMMA_MODEL", ""),
        "skill": plan.get("skill_name", "skill"),
        "input": user_input,
        "steps": trace_steps,
        "final_output": outputs[plan["steps"][-1]["id"]] if plan["steps"] else "",
        "totals": {"llm_calls": llm.stats.calls, "latency_ms": llm.stats.latency_ms,
                   "retries": retries, "cache_hits": llm.stats.cache_hits},
    }
    _emit(on_event, {"type": "run_end", "trace": trace})
    return trace
