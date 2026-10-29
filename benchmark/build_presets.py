"""Test the arena challenges (presets_src.py) against plain Gemma and the harness, then write attack_presets.json.

    python -m benchmark.build_presets --test  [--plain-runs 5] [--harness-runs 3] [--mode adaptive] [--only p01,p02]
    python -m benchmark.build_presets --build                       # offline: runs.json -> attack_presets.json

--test saves every run (full output, score, API errors) in benchmark/output/presets/runs.json after each run, so it can be
stopped and started again; finished runs are not repeated. --build reads that file only, no model calls.

Rules:
- A run whose model call failed (API error) is NOT a model failure: it is recorded as api_error, excluded from the counts, and
  repeated (up to 2 more times). A harness run counts as an API error only if it failed and one of its attempts hit an API error;
  a harness run that hit an error but still passed is a pass.
- The harness runs in the mode the arena uses by default (adaptive, ARENA_MODE), and the mode is saved in the file.
- tag: "reliable" if plain failed in at least 80% of its runs, "sometimes" if it failed in some but fewer, "untested" if it was
  not run. A challenge that never broke plain is NOT put in attack_presets.json; it is listed in dropped_presets.json.
- Everything in attack_presets.json that says "tested" comes from runs.json. Nothing is typed in by hand.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path

from benchmark import client, harness_adapter
from benchmark.presets_src import PRESET_SPECS
from benchmark.run_plain import run_plain
from benchmark.scorer import score_output

BENCH = Path(__file__).resolve().parent
RUNS_FILE = BENCH / "output" / "presets" / "runs.json"
PRESETS_FILE = BENCH / "attack_presets.json"
DROPPED_FILE = BENCH / "output" / "presets" / "dropped_presets.json"
RELIABLE_RATE = 0.8
EXTRA_TRIES = 2


# --- one run ------------------------------------------------------------------------------------------------------

def _record(spec: dict, mode: str, index: int, trace: dict | None, error: str | None) -> dict:
    rec = {"preset_id": spec["id"], "mode": mode, "index": index,
           "finished_at": datetime.now().astimezone().isoformat(timespec="seconds")}
    if trace is None:
        return {**rec, "passed": None, "failed_checks": [], "api_error": True, "error": error, "output": "",
                "llm_calls": 0, "latency_ms": 0}
    score = score_output(spec, trace.get("final_output", ""))
    rec.update({"passed": score["passed"], "failed_checks": score["failed_checks"], "error": None,
                "output": trace.get("final_output", ""), "llm_calls": trace["totals"]["llm_calls"],
                "latency_ms": trace["totals"]["latency_ms"]})
    api_attempts = [a["checker_note"] for s in trace.get("steps", []) for a in s["attempts"]
                    if str(a.get("checker_note", "")).startswith("LLM call failed")]
    rec["api_errors_in_run"] = len(api_attempts)
    if mode == "harness":
        rec["retries"] = trace["totals"].get("retries", 0)
        rec["steps"] = {k: sum(1 for s in trace["steps"] if s["status"] == k) for k in ("pass", "repaired", "fail")}
    rec["api_error"] = bool(api_attempts) and not score["passed"]
    if rec["api_error"]:
        rec["error"] = api_attempts[0]
    return rec


def run_once(spec: dict, mode: str, index: int, harness_mode: str) -> dict:
    """One plain or harness run of a preset. Never raises: a failed model call becomes an api_error record."""
    try:
        if mode == "plain":
            trace = run_plain(spec["skill_text"], spec["input"])
        else:
            trace = harness_adapter.run_skill(spec["skill_text"], spec["input"], mode=harness_mode)
    except Exception as exc:  # API outage, timeout, missing key: not a model failure
        return _record(spec, mode, index, None, f"{type(exc).__name__}: {exc}")
    return _record(spec, mode, index, trace, None)


# --- the runs file ------------------------------------------------------------------------------------------------

def current_settings(harness_mode: str) -> dict:
    return {**client.settings(), "verifier": harness_adapter.verifier_setting(), "harness_mode": harness_mode,
            "harness_is_mock": harness_adapter.HARNESS_IS_MOCK}


def load_runs(path: Path, settings: dict) -> dict:
    if not path.exists():
        return {"settings": {**settings, "started_at": datetime.now().astimezone().isoformat(timespec="seconds")}, "runs": []}
    doc = json.loads(path.read_text(encoding="utf-8"))
    for key in ("model", "provider", "gemma_thinking", "verifier", "harness_mode"):
        if doc["settings"].get(key) != settings.get(key):
            raise SystemExit(f"error: runs.json was made with {key}={doc['settings'].get(key)!r}, now {settings.get(key)!r}; "
                             f"use a different file or delete {path}")
    return doc


def save_runs(path: Path, doc: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")


def valid_runs(doc: dict, preset_id: str, mode: str) -> list[dict]:
    return [r for r in doc["runs"] if r["preset_id"] == preset_id and r["mode"] == mode and not r["api_error"]]


def test_presets(specs: list[dict], doc: dict, plain_runs: int, harness_runs: int, harness_mode: str,
                 sleep: float, save, run=run_once) -> dict:
    """Fill runs.json up to the wanted number of valid runs per preset and mode (api errors are repeated)."""
    for spec in specs:
        for mode, wanted in (("plain", plain_runs), ("harness", harness_runs)):
            tries = 0
            while len(valid_runs(doc, spec["id"], mode)) < wanted and tries < wanted + EXTRA_TRIES:
                index = len(valid_runs(doc, spec["id"], mode)) + 1
                rec = run(spec, mode, index, harness_mode)
                doc["runs"].append(rec)
                save(doc)
                tries += 1
                state = "API ERROR (not counted)" if rec["api_error"] else ("PASS" if rec["passed"] else f"FAIL {rec['failed_checks']}")
                print(f"{spec['id']} {mode:7} run {index}: {state}  calls={rec['llm_calls']}  {rec['latency_ms'] / 1000:.0f}s", flush=True)
                time.sleep(sleep)
    return doc


# --- the arena file -----------------------------------------------------------------------------------------------

def tag_for(failed: int, runs: int) -> str | None:
    """reliable / sometimes / untested, or None when plain never failed (the challenge is dropped)."""
    if runs == 0:
        return "untested"
    if failed == 0:
        return None
    return "reliable" if failed / runs >= RELIABLE_RATE else "sometimes"


def build_presets(specs: list[dict], doc: dict) -> tuple[list[dict], list[dict]]:
    """(presets for attack_presets.json, dropped challenges with the reason)."""
    s = doc["settings"]
    presets, dropped = [], []
    for spec in specs:
        plain, harness = valid_runs(doc, spec["id"], "plain"), valid_runs(doc, spec["id"], "harness")
        failed_plain = sum(1 for r in plain if not r["passed"])
        failed_harness = sum(1 for r in harness if not r["passed"])
        errors = sum(1 for r in doc["runs"] if r["preset_id"] == spec["id"] and r["api_error"])
        tag = tag_for(failed_plain, len(plain))
        if tag is None:
            dropped.append({"id": spec["id"], "title": spec["title"], "plain_runs": len(plain), "plain_failed": 0,
                            "reason": f"plain Gemma passed all {len(plain)} runs, so it is not a challenge that breaks it"})
            continue
        presets.append({
            "id": spec["id"], "title": spec["title"], "skill_text": spec["skill_text"], "input": spec["input"],
            "checks": spec["checks"], "steps": spec["steps"], "why_it_breaks": spec["why_it_breaks"], "tag": tag,
            "tested": {"model": s["model"], "date": s["started_at"][:10], "plain_runs": len(plain),
                       "plain_failed": failed_plain, "harness_runs": len(harness), "harness_failed": failed_harness,
                       "harness_mode": s["harness_mode"], "api_errors_excluded": errors},
        })
    return presets, dropped


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Test the arena challenges and write attack_presets.json.")
    ap.add_argument("--test", action="store_true", help="run the challenges against the model (API calls)")
    ap.add_argument("--build", action="store_true", help="write attack_presets.json from runs.json (offline)")
    ap.add_argument("--plain-runs", type=int, default=5)
    ap.add_argument("--harness-runs", type=int, default=3)
    ap.add_argument("--mode", default="adaptive", choices=["full", "adaptive", "auto"],
                    help="harness mode (default adaptive, what the arena uses unless ARENA_MODE says otherwise)")
    ap.add_argument("--only", help="comma-separated preset ids")
    ap.add_argument("--sleep", type=float, default=2.0)
    ap.add_argument("--runs-file", type=Path, default=RUNS_FILE)
    ap.add_argument("--out", type=Path, default=PRESETS_FILE)
    args = ap.parse_args(argv)
    if not (args.test or args.build):
        ap.error("give --test and/or --build")
    specs = [p for p in PRESET_SPECS if not args.only or p["id"] in set(args.only.split(","))]
    settings = current_settings(args.mode)
    if args.test:
        if harness_adapter.HARNESS_IS_MOCK:
            print("error: the real harness could not be imported; refusing to test presets with a stand-in", file=sys.stderr)
            return 1
        doc = load_runs(args.runs_file, settings)
        test_presets(specs, doc, args.plain_runs, args.harness_runs, args.mode, args.sleep, lambda d: save_runs(args.runs_file, d))
    if args.build:
        if not args.runs_file.exists():
            print(f"error: {args.runs_file} does not exist; run --test first", file=sys.stderr)
            return 1
        doc = json.loads(args.runs_file.read_text(encoding="utf-8"))
        presets, dropped = build_presets(PRESET_SPECS, doc)
        args.out.write_text(json.dumps(presets, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
        DROPPED_FILE.parent.mkdir(parents=True, exist_ok=True)
        DROPPED_FILE.write_text(json.dumps(dropped, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
        print(f"wrote {len(presets)} presets to {args.out}; dropped {len(dropped)}: {[d['id'] for d in dropped]}")
        for p in presets:
            t = p["tested"]
            print(f"  {p['id']} {p['tag']:9} plain failed {t['plain_failed']}/{t['plain_runs']}  harness failed {t['harness_failed']}/{t['harness_runs']}"
                  f"  api errors excluded {t['api_errors_excluded']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
