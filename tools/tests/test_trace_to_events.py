import json
import shutil
import subprocess
from pathlib import Path

import pytest

from tools.trace_to_events import main, trace_to_events

ROOT = Path(__file__).resolve().parents[2]
TRACES = sorted((ROOT / "skillcompiler" / "examples" / "traces").glob("*.json"))
NODE = shutil.which("node")


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.mark.parametrize("path", TRACES, ids=lambda p: p.name)
def test_events_follow_the_live_order(path):
    trace = load(path)
    events = trace_to_events(trace)
    kinds = [e["type"] for e in events]
    assert kinds[:2] == ["run_start", "plan"] and kinds[-1] == "run_end"
    assert events[-1]["trace"] == trace
    attempts = sum(len(s["attempts"]) for s in trace["steps"])
    assert kinds.count("attempt_start") == kinds.count("attempt_end") == attempts
    assert kinds.count("step_start") == kinds.count("step_end") == len(trace["steps"])
    for e in events:
        if e["type"] == "attempt_end":
            assert e["ok"] == (e["format_ok"] and e["verified"])


def test_a_trace_with_no_steps_goes_straight_to_the_end():
    plain = {"skill": "p", "mode": "plain", "steps": [], "totals": {"llm_calls": 1}, "final_output": "x",
             "mode_detail": {"strategy": "auto", "route": "plain", "reason": "easy"}}
    kinds = [e["type"] for e in trace_to_events(plain)]
    assert kinds == ["run_start", "route", "run_end"]


def test_cli_writes_ndjson(tmp_path):
    out = tmp_path / "e.ndjson"
    assert main([str(TRACES[0]), "-o", str(out)]) == 0
    lines = out.read_text(encoding="utf-8").splitlines()
    assert json.loads(lines[0])["type"] == "run_start" and json.loads(lines[-1])["type"] == "run_end"


@pytest.mark.skipif(NODE is None, reason="node is not installed")
@pytest.mark.parametrize("path", TRACES, ids=lambda p: p.name)
def test_python_and_javascript_converters_agree(path):
    """The page converts dropped traces in JS; the sample files are made in Python. They must match exactly."""
    js = ("const X=require('./web/xray-core.js');"
          "const t=JSON.parse(require('fs').readFileSync(process.argv[1],'utf8'));"
          "process.stdout.write(JSON.stringify(X.traceToEvents(t)))")
    out = subprocess.run([NODE, "-e", js, str(path)], cwd=ROOT, capture_output=True, text=True, encoding="utf-8", check=True).stdout
    assert json.loads(out) == trace_to_events(load(path))


@pytest.mark.skipif(NODE is None, reason="node is not installed")
def test_the_javascript_core_tests_pass():
    result = subprocess.run([NODE, "--test", "web/tests/xray-core.test.js"], cwd=ROOT, capture_output=True, text=True, encoding="utf-8")
    assert result.returncode == 0, result.stdout[-1500:] + result.stderr[-500:]
