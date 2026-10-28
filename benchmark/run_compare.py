"""Run plain Gemma and the harness on every task, score both, and write results.json and failures.json.

    python -m benchmark.run_compare [--limit N] [--resume] [--cache] [--no-verify] [--only t01,t02]

Output (default benchmark/output/): results.json, failures.json (contract 2.4) and traces/<task>_<mode>.json.
results.json also records, as extra optional fields, the settings that make the numbers comparable:
gemma_thinking, verifier ("on"/"off") and cache_used. Mock data is flagged with harness_is_mock: true
and a loud warning. A task whose model call errors out is NOT recorded
(an API outage is not a model failure); run again with --resume to retry it.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

from benchmark import client, harness_adapter
from benchmark.run_plain import ROOT, load_tasks, read_skill, run_plain
from benchmark.scorer import score_output

OUT_DIR = Path(__file__).with_name("output")
EXCERPT_CHARS = 300
SETTINGS_KEYS = ("model", "gemma_thinking", "verifier", "cache_used", "harness_is_mock")
MODES = ("plain", "harness")


def excerpt(text: str) -> str:
    text = (text or "").strip()
    return text if len(text) <= EXCERPT_CHARS else text[: EXCERPT_CHARS - 3] + "..."


def what_went_wrong(score: dict) -> str:
    parts = [f"{cid}: {score['details'][cid]}" for cid in score["failed_checks"]]
    return excerpt("; ".join(parts))


def step_summary(trace: dict) -> dict:
    counts = {"pass": 0, "repaired": 0, "fail": 0}
    for step in trace.get("steps", []):
        counts[step.get("status", "fail")] = counts.get(step.get("status", "fail"), 0) + 1
    return counts


def mode_entry(task: dict, trace: dict) -> dict:
    """One plain/harness cell of results.json (contract fields first, optional extras after)."""
    score = score_output(task, trace.get("final_output", ""))
    entry = {
        "passed": score["passed"],
        "failed_checks": score["failed_checks"],
        "failure_label": score["failure_label"],
        "llm_calls": trace["totals"]["llm_calls"],
        "latency_ms": trace["totals"]["latency_ms"],
        "output_excerpt": excerpt(trace.get("final_output", "")),
        "details": score["details"],
    }
    if trace.get("mode") == "harness":
        entry["retries"] = trace["totals"].get("retries", 0)
        entry["steps"] = step_summary(trace)
        entry["mock"] = bool(trace.get("mock"))
    return entry


def summarize(task_results: list[dict]) -> dict:
    return {m: {"passed": sum(t[m]["passed"] for t in task_results), "total": len(task_results)} for m in MODES}


def build_failures(task_results: list[dict]) -> list[dict]:
    """One entry per failed (task, mode), in task order."""
    out = []
    for t in task_results:
        for mode in MODES:
            cell = t[mode]
            if cell["passed"]:
                continue
            score = {"failed_checks": cell["failed_checks"], "details": cell["details"]}
            out.append({
                "failure_id": f"f{len(out) + 1:03d}", "task_id": t["task_id"], "mode": mode,
                "label": cell["failure_label"] or "other",
                "what_went_wrong": what_went_wrong(score),
                "failed_checks": cell["failed_checks"],
                "output_excerpt": cell["output_excerpt"],
            })
    return out


def current_settings(args: argparse.Namespace) -> dict:
    return {
        "model": client.current_model(),
        "gemma_thinking": client.thinking_level(),
        "verifier": harness_adapter.verifier_setting(),
        "cache_used": bool(args.cache),
        "harness_is_mock": harness_adapter.HARNESS_IS_MOCK,
    }


def write_outputs(out_dir: Path, settings: dict, task_results: list[dict]) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    results = {
        "model": settings["model"],
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "harness_is_mock": settings["harness_is_mock"],
        "gemma_thinking": settings["gemma_thinking"],
        "verifier": settings["verifier"],
        "cache_used": settings["cache_used"],
        "summary": summarize(task_results),
        "tasks": task_results,
    }
    (out_dir / "results.json").write_text(json.dumps(results, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    (out_dir / "failures.json").write_text(
        json.dumps(build_failures(task_results), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def load_previous(out_dir: Path, settings: dict) -> list[dict]:
    """Completed tasks from an earlier run. Refuses to mix runs made with different settings."""
    path = out_dir / "results.json"
    if not path.exists():
        return []
    old = json.loads(path.read_text(encoding="utf-8"))
    for key in SETTINGS_KEYS:
        if old.get(key) != settings[key]:
            raise SystemExit(f"error: --resume would mix settings: results.json has {key}={old.get(key)!r}, "
                             f"this run has {settings[key]!r}. Use a different --out-dir or delete {path}.")
    return [t for t in old["tasks"] if all(m in t for m in MODES)]


def run_one(task: dict, runners: dict) -> dict | None:
    """Run both modes for a task. Returns the results.json task entry, or None if a call errored."""
    skill_text = read_skill(task)
    cells, traces = {}, {}
    for mode in MODES:
        try:
            traces[mode] = runners[mode](skill_text, task["input"])
        except Exception as exc:  # API outage, missing key: not a model failure, so do not record it
            print(f"  ERROR in {mode} run of {task['task_id']}: {exc}", file=sys.stderr)
            return None
        cells[mode] = mode_entry(task, traces[mode])
        time.sleep(runners.get("sleep", 0))
    return {"task_id": task["task_id"], "title": task["title"], **cells, "_traces": traces}


def save_traces(out_dir: Path, entry: dict) -> None:
    tdir = out_dir / "traces"
    tdir.mkdir(parents=True, exist_ok=True)
    for mode, trace in entry.pop("_traces").items():
        (tdir / f"{entry['task_id']}_{mode}.json").write_text(
            json.dumps(trace, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="Compare plain Gemma with the harness on all tasks.")
    ap.add_argument("--limit", type=int, help="only the first N tasks")
    ap.add_argument("--only", help="comma-separated task ids")
    ap.add_argument("--resume", action="store_true", help="skip tasks already recorded in results.json")
    ap.add_argument("--cache", action="store_true", help="cache responses: for debugging, NOT for the final run")
    ap.add_argument("--no-verify", action="store_true", help="harness without its verifier call (SKILLCOMPILER_VERIFY=0)")
    ap.add_argument("--sleep", type=float, default=2.0, help="seconds between calls (default 2)")
    ap.add_argument("--out-dir", type=Path, default=OUT_DIR)
    ap.add_argument("--tasks", type=Path, help="tasks file (default benchmark/tasks.json)")
    return ap.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.no_verify:
        os.environ["SKILLCOMPILER_VERIFY"] = "0"
    client.configure_cache(args.cache)
    harness_adapter.configure_harness_cache(args.cache, str(Path(__file__).with_name(".cache") / "harness"))
    settings = current_settings(args)
    if harness_adapter.HARNESS_IS_MOCK:
        print("=" * 72 + "\n!! MOCK HARNESS: skillcompiler could not be imported "
              f"({harness_adapter.IMPORT_ERROR}).\n!! Harness numbers are a stand-in (plain Gemma). "
              "Do NOT report them.\n" + "=" * 72, file=sys.stderr)
    if args.cache:
        print("note: --cache is on; do not use these numbers as the final measured run.", file=sys.stderr)
    tasks = load_tasks(args.tasks, include_generated=args.tasks is None)
    if args.only:
        tasks = [t for t in tasks if t["task_id"] in set(args.only.split(","))]
    done = load_previous(args.out_dir, settings) if args.resume else []
    done_ids = {t["task_id"] for t in done}
    todo = [t for t in tasks if t["task_id"] not in done_ids]
    todo = todo[: args.limit] if args.limit else todo
    runners = {"plain": run_plain, "harness": harness_adapter.run_skill, "sleep": args.sleep}
    results = list(done)
    for task in todo:
        print(f"{task['task_id']}  {task['title']}", flush=True)
        entry = run_one(task, runners)
        if entry is None:
            continue
        save_traces(args.out_dir, entry)
        results.append(entry)
        results.sort(key=lambda t: t["task_id"])
        write_outputs(args.out_dir, settings, results)  # after every task, so --resume can pick up
        print("  plain {}   harness {}".format(*("PASS" if entry[m]["passed"] else "FAIL" for m in MODES)), flush=True)
    write_outputs(args.out_dir, settings, results)
    s = summarize(results)
    print(f"\nplain {s['plain']['passed']}/{s['plain']['total']}   harness {s['harness']['passed']}/{s['harness']['total']}"
          f"   settings={ {k: settings[k] for k in SETTINGS_KEYS} }")
    if harness_adapter.HARNESS_IS_MOCK:
        print("!! MOCK harness numbers above are not results.", file=sys.stderr)
    skipped = len(tasks) - len(results)
    if skipped and not args.limit:
        print(f"{skipped} task(s) not recorded (errors); run again with --resume.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
