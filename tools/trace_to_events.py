"""Convert a trace.json into the NDJSON event sequence a live run produces (skillcompiler/stream.py).

    python tools/trace_to_events.py skillcompiler/examples/traces/X.json -o web/mock/events_x.ndjson

The X-ray page replays these files. The same conversion exists in web/xray-core.js (traceToEvents) so any
trace.json can be dropped on the page; a test checks that the two agree.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def trace_to_events(trace: dict) -> list[dict]:
    """run_start, [route], plan, then step_start / attempt_start / attempt_end / step_end per step, then run_end."""
    detail = trace.get("mode_detail") or {}
    events: list[dict] = [{"type": "run_start", "will_split": True, "mode": detail.get("strategy", "full")}]
    if detail.get("route"):
        events.append({"type": "route", "route": detail["route"], "reason": detail.get("reason", "")})
    if not trace["steps"]:  # a plain-route run has no steps
        events.append({"type": "run_end", "trace": trace})
        return events
    events.append({"type": "plan", "skill": trace["skill"], "warnings": [],
                   "steps": [{"id": s["step_id"], "title": s["title"], "instruction": s.get("instruction", "")}
                             for s in trace["steps"]]})
    for step in trace["steps"]:
        events.append({"type": "step_start", "step_id": step["step_id"], "title": step["title"]})
        for i, attempt in enumerate(step["attempts"], start=1):
            start = {"type": "attempt_start", "step_id": step["step_id"], "attempt": i}
            if attempt.get("model"):
                start["model"] = attempt["model"]
            events.append(start)
            ok = bool(attempt["format_ok"] and attempt["verified"])
            events.append({"type": "attempt_end", "step_id": step["step_id"], "attempt": i, "ok": ok, **attempt})
        events.append({"type": "step_end", "step_id": step["step_id"], "status": step["status"]})
    events.append({"type": "run_end", "trace": trace})
    return events


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="trace.json -> NDJSON events")
    parser.add_argument("trace", help="path to a trace.json")
    parser.add_argument("-o", "--output", help="write here (default: print)")
    args = parser.parse_args(argv)
    trace = json.loads(Path(args.trace).read_text(encoding="utf-8"))
    text = "".join(json.dumps(e, ensure_ascii=False) + "\n" for e in trace_to_events(trace))
    if args.output:
        Path(args.output).write_text(text, encoding="utf-8")
        print(f"wrote {args.output} ({text.count(chr(10))} events)", file=sys.stderr)
    else:
        sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
