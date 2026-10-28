"""What the harness costs: calls and latency per task, plain vs harness. Reads results.json, writes overhead.md.

    python -m benchmark.overhead [--results benchmark/output/results.json] [--out benchmark/output/overhead.md]

No model calls. The settings (model, GEMMA_THINKING, verifier, tasks hash, mock flag) are copied from results.json
so the table can never be separated from the conditions it was measured under.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

OUT = Path(__file__).with_name("output")


def ratio(a: float, b: float) -> str:
    return f"{a / b:.1f}x" if b else "n/a"


def thinking_text(value: str) -> str:
    return "unset (default MINIMAL)" if value == "MINIMAL" else value


def build_report(results: dict) -> str:
    tasks = results["tasks"]
    n = len(tasks)
    sums = {m: {"calls": sum(t[m]["llm_calls"] for t in tasks), "ms": sum(t[m]["latency_ms"] for t in tasks)}
            for m in ("plain", "harness")}
    sha = results.get("tasks_sha256", "unknown")
    lines = [
        "# Overhead: plain vs harness",
        "",
        "Measured on the 10 frozen tasks, one run. Every number comes from `results.json`.",
        "",
        "| Setting | Value |",
        "|---|---|",
        f"| Model | `{results['model']}` |",
        f"| GEMMA_THINKING | {thinking_text(results['gemma_thinking'])} |",
        f"| Verifier | {results['verifier'].upper()} |",
        f"| Cache | {'ON' if results['cache_used'] else 'OFF'} |",
        f"| Harness is mock | {'YES' if results['harness_is_mock'] else 'no'} |",
        f"| tasks.json SHA-256 | `{sha[:8]}` (`{sha}`) |",
        f"| Run time | {results['generated_at']} |",
        "",
        "## Per task",
        "",
        "| Task | Plain calls | Harness calls | Calls ratio | Plain latency (s) | Harness latency (s) | Latency ratio | Plain | Harness |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for t in tasks:
        p, h = t["plain"], t["harness"]
        lines.append(
            f"| {t['task_id']} | {p['llm_calls']} | {h['llm_calls']} | {ratio(h['llm_calls'], p['llm_calls'])} "
            f"| {p['latency_ms'] / 1000:.1f} | {h['latency_ms'] / 1000:.1f} | {ratio(h['latency_ms'], p['latency_ms'])} "
            f"| {'PASS' if p['passed'] else 'FAIL'} | {'PASS' if h['passed'] else 'FAIL'} |")
    sp, sh = sums["plain"], sums["harness"]
    lines += [
        "",
        "## Totals and averages",
        "",
        "| | Plain | Harness | Ratio |",
        "|---|---|---|---|",
        f"| Calls, total | {sp['calls']} | {sh['calls']} | {ratio(sh['calls'], sp['calls'])} |",
        f"| Calls, per task | {sp['calls'] / n:.1f} | {sh['calls'] / n:.1f} | {ratio(sh['calls'], sp['calls'])} |",
        f"| Latency, total (s) | {sp['ms'] / 1000:.0f} | {sh['ms'] / 1000:.0f} | {ratio(sh['ms'], sp['ms'])} |",
        f"| Latency, per task (s) | {sp['ms'] / n / 1000:.1f} | {sh['ms'] / n / 1000:.1f} | {ratio(sh['ms'], sp['ms'])} |",
        "",
        "Latency is the sum of the model calls' time as recorded in each trace; it does not include the 2 s pause "
        "between runs or the rate limiter's waits.",
        "",
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Write overhead.md from results.json.")
    ap.add_argument("--results", type=Path, default=OUT / "results.json")
    ap.add_argument("--out", type=Path, default=OUT / "overhead.md")
    args = ap.parse_args(argv)
    report = build_report(json.loads(args.results.read_text(encoding="utf-8")))
    args.out.write_text(report, encoding="utf-8", newline="\n")
    print(report)
    return 0


if __name__ == "__main__":
    sys.exit(main())
