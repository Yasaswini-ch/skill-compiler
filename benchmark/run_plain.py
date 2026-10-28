"""Plain baseline: the whole SKILL.md plus the input in ONE model call, with no help.

run_plain(skill_text, user_input, model=None) -> trace.json dict, mode "plain".

Batch use (scores every task, prints a summary, no harness involved):
    python -m benchmark.run_plain [--limit N] [--cache] [--only t01,t02]
"""
from __future__ import annotations

import argparse
import itertools
import json
import re
import sys
import time
from pathlib import Path

from benchmark import client
from benchmark.scorer import score_output

ROOT = Path(__file__).resolve().parents[1]
_run_ids = itertools.count(1)


def plain_prompt(skill_text: str, user_input: str) -> str:
    """The baseline prompt: the skill as written, then the input. Nothing else."""
    return f"{skill_text.strip()}\n\nInput:\n{user_input.strip()}"


def skill_name(skill_text: str) -> str:
    match = re.search(r"^name:\s*(\S+)", skill_text, re.MULTILINE)
    return match.group(1) if match else "skill"


def run_plain(skill_text: str, user_input: str, model: str | None = None) -> dict:
    """One model call. Returns a trace.json dict (mode "plain", no steps, mock false)."""
    client.stats.reset()
    start = time.time()
    output = client.call_llm(plain_prompt(skill_text, user_input), model)
    latency_ms = client.stats.latency_ms or int((time.time() - start) * 1000)
    return {
        "run_id": f"plain-{next(_run_ids):03d}",
        "mode": "plain",
        "mock": False,
        "model": model or client.current_model(),
        "skill": skill_name(skill_text),
        "input": user_input,
        "steps": [],
        "final_output": output,
        "totals": {"llm_calls": client.stats.calls, "latency_ms": latency_ms, "retries": 0,
                   "cache_hits": client.stats.cache_hits},
    }


def load_tasks(path: Path | None = None, include_generated: bool = False) -> list[dict]:
    path = path or Path(__file__).with_name("tasks.json")
    tasks = json.loads(path.read_text(encoding="utf-8"))
    generated = path.with_name("tasks_generated.json")
    if include_generated and generated.exists():
        tasks += json.loads(generated.read_text(encoding="utf-8"))
    return tasks


def read_skill(task: dict) -> str:
    return (ROOT / task["skill_file"]).read_text(encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Run plain Gemma on every task and score it.")
    ap.add_argument("--limit", type=int, help="only the first N tasks")
    ap.add_argument("--only", help="comma-separated task ids")
    ap.add_argument("--cache", action="store_true", help="cache responses (debugging only)")
    ap.add_argument("--sleep", type=float, default=2.0, help="seconds between calls (default 2)")
    args = ap.parse_args(argv)
    client.configure_cache(args.cache)
    tasks = load_tasks(include_generated=True)
    if args.only:
        wanted = set(args.only.split(","))
        tasks = [t for t in tasks if t["task_id"] in wanted]
    tasks = tasks[: args.limit] if args.limit else tasks
    passed = 0
    for task in tasks:
        trace = run_plain(read_skill(task), task["input"])
        score = score_output(task, trace["final_output"])
        passed += score["passed"]
        print(f"{task['task_id']}  {'PASS' if score['passed'] else 'FAIL'}  failed={score['failed_checks']}  "
              f"label={score['failure_label']}", flush=True)
        time.sleep(args.sleep)
    print(f"\nplain: {passed}/{len(tasks)} passed  settings={client.settings()}  cache={args.cache}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
