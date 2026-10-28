"""Ask Gemma to rewrite a SKILL.md for small models, then measure whether that helps plain Gemma.

    python -m benchmark.autorewrite skills/trip-day-planner/SKILL.md [--only t07] [--repeats 1]

1. Gemma rewrites the skill (one action per step, numbered steps, every constraint inside its step, no vague words,
   exact output format at the end) and the result is saved next to the original as SKILL.rewritten.md.
2. Every number and quoted phrase of the original that is missing from the rewrite is printed as a WARNING: a rewrite
   that quietly drops a constraint would make the "after" score meaningless.
3. Plain Gemma (one call, no harness) runs the same tasks with the original and with the rewritten skill, both are
   scored by scorer.py, and a before/after table is printed. The report with all outputs is saved as JSON.

The tasks are the ones in tasks.json that use this skill (read only). Same model, GEMMA_THINKING and pacing for both
versions. Report the table as measured, whatever it shows; with few tasks and one run it is not a statistical result.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import time
from datetime import datetime
from pathlib import Path

from benchmark import client
from benchmark.run_plain import ROOT, load_tasks, plain_prompt
from benchmark.scorer import score_output

BENCH = Path(__file__).resolve().parent
OUT_DIR = BENCH / "output" / "autorewrite"

PROMPT = """Rewrite the agent skill below so that a small language model can follow it reliably.

Rules:
- One action per step.
- Number the steps.
- Put every constraint (word limits, allowed values, required phrases, forbidden words) inside the step it applies to.
- Remove vague words such as "appropriate", "as needed", "properly", "relevant", "if necessary", "etc.".
- State the exact output format at the end.
- Keep the YAML frontmatter (name and description) at the top, unchanged.
- Keep every requirement of the original. Do not add requirements and do not drop any, and keep every number, quoted phrase and allowed value exactly as written.
- Return ONLY the rewritten SKILL.md, no explanation.

SKILL.md:
{skill_text}
"""


def clean_rewrite(reply: str) -> str:
    """The model's reply as a file: whole-reply code fence removed, trailing newline."""
    s = (reply or "").strip()
    fence = re.match(r"\A```[A-Za-z0-9_-]*[ \t]*\r?\n(.*?)\r?\n?```\Z", s, re.DOTALL)
    return (fence.group(1).strip() if fence else s) + "\n"


def lost_constraints(original: str, rewritten: str) -> list[str]:
    """Numbers and quoted phrases that appear in the original skill but not in the rewrite."""
    numbers = dict.fromkeys(re.findall(r"\d+(?:\.\d+)?", original))
    quoted = dict.fromkeys(re.findall(r'"([^"\n]+)"', original))
    lost = [f"number {n}" for n in numbers if not re.search(rf"(?<![\d.]){re.escape(n)}(?![\d])", rewritten)]
    lost += [f'phrase "{q}"' for q in quoted if q not in rewritten]
    return lost


def relative_skill(path: Path) -> str:
    return path.resolve().relative_to(ROOT).as_posix()


def run_versions(tasks: list[dict], versions: dict[str, str], repeats: int, call, sleep: float) -> list[dict]:
    """Plain runs of every task with every skill version. Returns one row per (task, version, repeat)."""
    rows = []
    for task in tasks:
        for name, skill_text in versions.items():
            for rep in range(1, repeats + 1):
                output = call(plain_prompt(skill_text, task["input"]))
                score = score_output(task, output)
                rows.append({"task_id": task["task_id"], "version": name, "repeat": rep, "passed": score["passed"],
                             "failed_checks": score["failed_checks"], "failure_label": score["failure_label"],
                             "output": output})
                print(f"  {task['task_id']} {name:9} run {rep}: {'PASS' if score['passed'] else 'FAIL'} {score['failed_checks']}",
                      flush=True)
                time.sleep(sleep)
    return rows


def before_after(rows: list[dict], task_ids: list[str], repeats: int) -> str:
    """The before/after table as text."""
    def cell(tid, version):
        r = [x for x in rows if x["task_id"] == tid and x["version"] == version]
        return f"{sum(x['passed'] for x in r)}/{len(r)}", sorted({c for x in r for c in x["failed_checks"]})

    lines = [f"{'task':8} {'original':>9} {'rewritten':>10}   failed checks (original | rewritten)"]
    for tid in task_ids:
        (a, fa), (b, fb) = cell(tid, "original"), cell(tid, "rewritten")
        lines.append(f"{tid:8} {a:>9} {b:>10}   {fa or '-'} | {fb or '-'}")
    tot = {v: sum(x["passed"] for x in rows if x["version"] == v) for v in ("original", "rewritten")}
    n = len(task_ids) * repeats
    before, after = f"{tot['original']}/{n}", f"{tot['rewritten']}/{n}"
    lines.append(f"{'TOTAL':8} {before:>9} {after:>10}")
    return "\n".join(lines)


def main(argv: list[str] | None = None, call=None) -> int:
    ap = argparse.ArgumentParser(description="Rewrite a skill for small models and measure the effect with plain Gemma.")
    ap.add_argument("skill", type=Path, help="path to a SKILL.md")
    ap.add_argument("--only", help="comma-separated task ids (default: all tasks that use this skill)")
    ap.add_argument("--repeats", type=int, default=1, help="plain runs per task and version (default 1)")
    ap.add_argument("--tasks", type=Path, help="tasks file (default benchmark/tasks.json)")
    ap.add_argument("--sleep", type=float, default=2.0, help="seconds between calls (default 2)")
    ap.add_argument("--out", type=Path, help="report JSON (default benchmark/output/autorewrite/<skill>.json)")
    args = ap.parse_args(argv)
    call = call or client.call_llm
    skill_path = args.skill.resolve()
    original = skill_path.read_text(encoding="utf-8")
    rel = relative_skill(skill_path)
    tasks = [t for t in load_tasks(args.tasks) if t["skill_file"] == rel]
    if args.only:
        tasks = [t for t in tasks if t["task_id"] in set(args.only.split(","))]
    if not tasks:
        print(f"error: no tasks use {rel}", file=sys.stderr)
        return 1

    print(f"rewriting {rel} ...", flush=True)
    rewritten = clean_rewrite(call(PROMPT.format(skill_text=original.strip())))
    target = skill_path.with_name("SKILL.rewritten.md")
    target.write_text(rewritten, encoding="utf-8", newline="\n")
    warnings = lost_constraints(original, rewritten)
    if not rewritten.startswith("---"):
        warnings.append("the frontmatter at the top is missing")
    for w in warnings:
        print(f"  WARNING, missing from the rewrite: {w}", file=sys.stderr)

    rows = run_versions(tasks, {"original": original, "rewritten": rewritten}, args.repeats, call, args.sleep)
    ids = [t["task_id"] for t in tasks]
    table = before_after(rows, ids, args.repeats)
    print("\n" + table)
    if warnings:
        print(f"\n{len(warnings)} warning(s): the rewrite does not contain everything the original had.", file=sys.stderr)

    out = args.out or OUT_DIR / f"{skill_path.parent.name}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    report = {"generated_at": datetime.now().astimezone().isoformat(timespec="seconds"), "skill": rel,
              "rewritten_file": relative_skill(target), "settings": client.settings(), "repeats": args.repeats,
              "rewrite_warnings": warnings, "original_sha256": hashlib.sha256(original.encode("utf-8")).hexdigest(),
              "rewritten_sha256": hashlib.sha256(rewritten.encode("utf-8")).hexdigest(), "table": table, "runs": rows}
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    print(f"\nreport: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
