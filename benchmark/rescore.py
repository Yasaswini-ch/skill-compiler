"""Re-score a saved plain_baseline.json with the current tasks.json. Offline: no API calls.

    python -m benchmark.rescore [benchmark/output/plain_baseline.json]

The saved model outputs are kept as they are; only the scores are recomputed. The file records what it
was scored with before (tasks hash and pass count), so a re-score after a documented check fix is visible.
"""
from __future__ import annotations

import hashlib
import json
import sys
from datetime import datetime
from pathlib import Path

from benchmark.run_plain import load_tasks
from benchmark.scorer import score_output

DEFAULT = Path(__file__).with_name("output") / "plain_baseline.json"
TASKS_FILE = Path(__file__).with_name("tasks.json")


def rescore(report: dict, tasks: list[dict], tasks_sha256: str) -> dict:
    """Return a copy of the report with every row re-scored against `tasks`."""
    by_id = {t["task_id"]: t for t in tasks}
    rows = []
    for row in report["tasks"]:
        score = score_output(by_id[row["task_id"]], row["output"])
        rows.append({**row, **score})
    passed = sum(r["passed"] for r in rows)
    history = report.get("rescored", [])
    history.append({"at": datetime.now().astimezone().isoformat(timespec="seconds"),
                    "previous_tasks_sha256": report["tasks_sha256"],
                    "previous_summary": report["summary"]})
    return {**report, "tasks_sha256": tasks_sha256, "summary": {"passed": passed, "total": len(rows)},
            "tasks": rows, "rescored": history}


def main(argv: list[str] | None = None) -> int:
    path = Path((argv or sys.argv[1:] or [str(DEFAULT)])[0])
    report = json.loads(path.read_text(encoding="utf-8"))
    sha = hashlib.sha256(TASKS_FILE.read_bytes()).hexdigest()
    new = rescore(report, load_tasks(TASKS_FILE), sha)
    old_by_id = {r["task_id"]: r["passed"] for r in report["tasks"]}
    for r in new["tasks"]:
        changed = "" if old_by_id[r["task_id"]] == r["passed"] else f"   (was {'PASS' if old_by_id[r['task_id']] else 'FAIL'})"
        print(f"{r['task_id']}  {'PASS' if r['passed'] else 'FAIL'}  failed={r['failed_checks']}{changed}")
    s = new["summary"]
    print(f"\nplain: {s['passed']}/{s['total']} passed (was {report['summary']['passed']}/{report['summary']['total']})"
          f"  tasks sha256 {sha[:12]}")
    path.write_text(json.dumps(new, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
