"""Run a skill step by step: prompt, check, retry with feedback, write a trace."""
from __future__ import annotations

import os
import re
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
{rule}Reply with only the output for this step. No explanation, no extra text.
"""

def copy_rule_enabled() -> bool:
    """SKILLCOMPILER_COPY_RULE=1 adds COPY_RULE to JSON assembly steps. Off by default: it fixed benchmark
    task t03 (3 of 3 re-runs) but has not been shown to help overall, so the default stays as in the
    official runs until a measured comparison says otherwise."""
    return os.environ.get("SKILLCOMPILER_COPY_RULE", "0") == "1"


# A final step that assembles JSON from earlier results tended to "tidy" them: the text "no"
# came out as the boolean false (benchmark task t03), which broke an exact-value check.
COPY_RULE = ("When you put earlier results into the JSON, copy each one exactly as written: do not "
             "reword it and do not change its type (keep \"yes\" or \"no\" as text, not true or "
             "false, and keep numbers as numbers).\n\n")

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


MODES = ("full", "adaptive")
HARD_RULE_RE = re.compile(
    r"\b(at most|at least|no more than|exactly|must (?:begin|start|not)|never|only)\b", re.IGNORECASE)
ARITHMETIC_RE = re.compile(
    r"\b(add|sum|subtract|minus|plus|multipl\w*|divid\w*|times|percent\w*|tax|discount|average|"
    r"total|compute|calculate)\b", re.IGNORECASE)
OPERATOR_RE = re.compile(r"\d\s*[-+*/×x%]\s*\d|%")


def is_risky(step: dict, plan: dict) -> bool:
    """Steps worth a model verification call in adaptive mode. The format and rule checks run
    for every step either way; this decides only whether the extra verifier call is made.

    Risky: a strict output format, arithmetic, a hard rule (at most, exactly, must begin with,
    never, only), a dependence on two or more earlier steps, or being the final step.
    """
    instruction = step.get("instruction", "")
    return (
        (step.get("output_format") or "text") != "text"
        or bool(ARITHMETIC_RE.search(instruction) or OPERATOR_RE.search(instruction))
        or bool(HARD_RULE_RE.search(instruction))
        or len(step.get("depends_on", [])) >= 2
        or step.get("id") == plan["steps"][-1]["id"]
    )


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
        rule=COPY_RULE if (earlier and step.get("output_format") == "json" and copy_rule_enabled()) else "",
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
        if (format_ok and not verified and attempts
                and attempts[-1]["format_ok"] and attempts[-1]["output"] == output):
            # The model gave the same answer twice IN A ROW and only the model verifier
            # objects. Its judgement can be wrong (it once rejected a correct sum), so keep
            # the answer. An answer the model gave, dropped and came back to is NOT covered:
            # in benchmark task t04 the verifier was right twice, the model flip-flopped back
            # to its first wrong answer, and accepting it hid a failure behind "repaired".
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
    _emit(on_event, {"type": "step_end", "step_id": step["id"], "status": status,
                     "verified": bool(verify)})
    return entry, output


def run_skill(skill_text: str, user_input: str, model: str | None = None,
              max_retries: int = 2, verify: bool | None = None,
              plan: dict | None = None,
              on_event: Callable[[dict], None] | None = None,
              mode: str | None = None) -> dict:
    """Split (unless a plan is given), run every step, return a trace.json dict.

    mode "full" (default) calls the model verifier on every step. mode "adaptive" calls it only on
    risky steps (see is_risky); the format and rule checks run on every step in both modes, and
    verify=False (or SKILLCOMPILER_VERIFY=0) turns the verifier off in both. SKILLCOMPILER_MODE sets
    the default mode; an explicit argument wins. Adaptive runs add trace["mode_detail"].

    on_event, if given, is called with a plain dict as the run progresses, so a UI can show
    steps as they finish: run_start, plan, step_start, attempt_start, attempt_end, step_end,
    run_end (carrying the full trace). It is called from the running thread and an
    exception raised inside it is ignored.
    """
    if verify is None:  # SKILLCOMPILER_VERIFY=0 switches the verifier call off globally
        verify = os.environ.get("SKILLCOMPILER_VERIFY", "1") != "0"
    mode = mode or os.environ.get("SKILLCOMPILER_MODE", "full")
    if mode not in MODES:
        raise ValueError(f"unknown mode {mode!r}; use one of: {', '.join(MODES)}")
    llm.stats.reset()
    _emit(on_event, {"type": "run_start", "will_split": plan is None, "mode": mode})
    plan = plan or compile_skill(skill_text, model)
    _emit(on_event, {"type": "plan", "skill": plan.get("skill_name", "skill"),
                     "steps": [{"id": st["id"], "title": st["title"]} for st in plan["steps"]],
                     "warnings": plan.get("warnings", [])})
    outputs: dict[int, str] = {}
    titles = {s["id"]: s["title"] for s in plan["steps"]}
    trace_steps = []
    verified_steps: list[int] = []
    skipped_steps: list[int] = []
    for step in plan["steps"]:
        step_verify = bool(verify) and (mode == "full" or is_risky(step, plan))
        (verified_steps if step_verify else skipped_steps).append(step["id"])
        entry, output = _run_step(step, user_input, outputs, titles, model,
                                  max_retries, step_verify, on_event)
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
    if mode == "adaptive":  # optional contract field; full-mode traces stay exactly as before
        trace["mode_detail"] = {"strategy": "adaptive", "route": "harness",
                                "verified_steps": verified_steps, "skipped_verify_steps": skipped_steps}
    _emit(on_event, {"type": "run_end", "trace": trace})
    return trace
