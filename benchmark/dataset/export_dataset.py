"""Export the official run 1 failures and the tasks used as JSONL into benchmark/dataset/.

    python -m benchmark.dataset.export_dataset

Reads benchmark/output/results.json, failures.json and benchmark/tasks.json (run 1 is the official run).
Writes:
  failures.jsonl  one failure per line, with its task, the reviewed label, the scorer's own label (when a
                  person changed it) and the settings the run was made with.
  tasks.jsonl     the tasks used, one per line, with the full skill text embedded so a line is self-contained.

No model calls. Stops with an error if results.json was made with a different tasks.json than the one on disk.
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

BENCH = Path(__file__).resolve().parents[1]
ROOT = BENCH.parent
OUT_DIR = Path(__file__).resolve().parent
LABELS = {"skipped_step", "wrong_format", "lost_track", "merged_steps", "hallucinated_step",
          "ignored_constraint", "other"}


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def failure_records(results: dict, failures: list[dict], tasks: list[dict]) -> list[dict]:
    """One record per failure in failures.json, enriched from results.json and tasks.json."""
    by_id = {t["task_id"]: t for t in tasks}
    cells = {(t["task_id"], m): t[m] for t in results["tasks"] for m in ("plain", "harness")}
    out = []
    for f in failures:
        task, cell = by_id[f["task_id"]], cells[(f["task_id"], f["mode"])]
        if f["label"] not in LABELS:
            raise ValueError(f"{f['failure_id']}: unknown label {f['label']!r}")
        if cell["passed"]:
            raise ValueError(f"{f['failure_id']}: results.json says {f['task_id']} {f['mode']} passed")
        rec = {
            "failure_id": f["failure_id"], "task_id": f["task_id"], "task_title": task["title"],
            "difficulty_tags": task["difficulty_tags"], "mode": f["mode"], "label": f["label"],
            "what_went_wrong": f["what_went_wrong"], "failed_checks": f["failed_checks"],
            "output_excerpt": f["output_excerpt"],
        }
        if cell.get("scorer_label") and cell["scorer_label"] != f["label"]:
            rec["scorer_label"] = cell["scorer_label"]
        if f.get("label_note"):
            rec["label_note"] = f["label_note"]
        rec.update({"run": 1, "model": results["model"], "verifier": results["verifier"],
                    "gemma_thinking": results["gemma_thinking"], "tasks_sha256": results["tasks_sha256"]})
        out.append(rec)
    return out


def task_records(tasks: list[dict], read_skill) -> list[dict]:
    """The tasks as given, plus the skill text they use."""
    return [{**t, "skill_text": read_skill(t["skill_file"])} for t in tasks]


def write_jsonl(path: Path, records: list[dict]) -> None:
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        for rec in records:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def main() -> int:
    out = BENCH / "output"
    results = json.loads((out / "results.json").read_text(encoding="utf-8"))
    failures = json.loads((out / "failures.json").read_text(encoding="utf-8"))
    tasks_file = BENCH / "tasks.json"
    tasks = json.loads(tasks_file.read_text(encoding="utf-8"))
    if results.get("tasks_sha256") != sha256_file(tasks_file):
        print("error: results.json was made with a different tasks.json than the one on disk", file=sys.stderr)
        return 1
    if results.get("harness_is_mock") or results.get("cache_used"):
        print("error: results.json is a mock or cached run; it is not an official run", file=sys.stderr)
        return 1
    frecs = failure_records(results, failures, tasks)
    trecs = task_records(tasks, lambda p: (ROOT / p).read_text(encoding="utf-8"))
    write_jsonl(OUT_DIR / "failures.jsonl", frecs)
    write_jsonl(OUT_DIR / "tasks.jsonl", trecs)
    print(f"wrote {len(frecs)} failures and {len(trecs)} tasks to {OUT_DIR}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
