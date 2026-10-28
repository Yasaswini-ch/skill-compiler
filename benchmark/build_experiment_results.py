"""Build the model comparison table (experiment_results.json, contract/phase2) from saved results.json files.

    python -m benchmark.build_experiment_results \
        --run "Gemma 4 26B A4B (Gemini API)=benchmark/output/results.json" \
        --note "Gemma 4 26B A4B (Gemini API)=official run 1 of 3" \
        [--run "NAME=other/results.json" ...] [--out benchmark/experiment_results.json]

Every number comes from a results.json written by run_compare. Each --run gives two rows: plain and harness. There is no
adaptive row unless a saved results.json of an adaptive run is given: the numbers in docs/HARNESS.md section 14 come from
runs whose per-task outputs were not saved, so they are not used here. Nothing is typed in by hand.

passed/total/llm_calls/latency_s are the totals of ONE run over all tasks (runs_per_config is 1). The harness commit is the
last commit that touched skillcompiler/ before the (first) run finished, read from git history.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = Path(__file__).with_name("experiment_results.json")


def harness_commit(generated_at: str) -> str | None:
    """Short hash of the last commit that touched skillcompiler/ before `generated_at`; None if git cannot tell."""
    try:
        out = subprocess.run(["git", "log", "-1", "--format=%h", f"--before={generated_at}", "--", "skillcompiler"],
                             cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return None
    return out or None


def rows_for(name: str, results: dict, note: str | None) -> list[dict]:
    """The plain row and the harness row of one results.json."""
    provider = results.get("provider", "gemini")
    rows = []
    for mode in ("plain", "harness"):
        cells = [(t["task_id"], t[mode]) for t in results["tasks"]]
        row = {
            "name": f"{name}, {mode}", "model": results["model"], "provider": provider, "mode": mode,
            "passed": sum(1 for _, c in cells if c["passed"]), "total": len(cells),
            "llm_calls": sum(c["llm_calls"] for _, c in cells),
            "latency_s": round(sum(c["latency_ms"] for _, c in cells) / 1000, 1),
            "failed_tasks": [tid for tid, c in cells if not c["passed"]],
        }
        if note:
            row["notes"] = note
        rows.append(row)
    return rows


def build(runs: list[tuple[str, Path]], notes: dict[str, str]) -> dict:
    loaded = [(name, json.loads(path.read_text(encoding="utf-8"))) for name, path in runs]
    first = loaded[0][1]
    for name, r in loaded:
        if r["tasks_sha256"] != first["tasks_sha256"] or len(r["tasks"]) != len(first["tasks"]):
            raise ValueError(f"{name}: a different task set than the first run; they cannot share one table")
    configs = [row for name, r in loaded for row in rows_for(name, r, notes.get(name))]
    doc = {
        "mock": any(r.get("harness_is_mock") for _, r in loaded),
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "tasks_file": "benchmark/tasks.json",
        "tasks_sha256": first["tasks_sha256"],
        "n_tasks": len(first["tasks"]),
        "settings": {"thinking": first["gemma_thinking"], "verifier": first["verifier"],
                     "cache": any(r["cache_used"] for _, r in loaded), "runs_per_config": 1},
        "configs": configs,
    }
    commit = harness_commit(first["generated_at"])
    if commit:
        doc["harness_commit"] = commit
    return doc


def split_pairs(items: list[str], what: str) -> list[tuple[str, str]]:
    pairs = []
    for item in items:
        if "=" not in item:
            raise ValueError(f'{what} must look like "NAME=VALUE", got {item!r}')
        name, value = item.split("=", 1)
        pairs.append((name.strip(), value.strip()))
    return pairs


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Build experiment_results.json from saved results.json files.")
    ap.add_argument("--run", action="append", required=True, metavar="NAME=PATH", help="a results.json to include")
    ap.add_argument("--note", action="append", default=[], metavar="NAME=TEXT", help="a note for that run's rows")
    ap.add_argument("--out", type=Path, default=OUT)
    args = ap.parse_args(argv)
    try:
        runs = [(n, Path(p)) for n, p in split_pairs(args.run, "--run")]
        doc = build(runs, dict(split_pairs(args.note, "--note")))
    except (ValueError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    args.out.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    for c in doc["configs"]:
        print(f"{c['name']:48} {c['passed']}/{c['total']}  calls {c['llm_calls']}  {c['latency_s']} s  failed {c['failed_tasks']}")
    print(f"wrote {args.out}  (mock={doc['mock']}, harness_commit={doc.get('harness_commit')})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
