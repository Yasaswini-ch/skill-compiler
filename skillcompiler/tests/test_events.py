import json
import threading
import time

import pytest

from skillcompiler import llm, run_skill, runner
from skillcompiler.stream import ndjson_events

PLAN = {"skill_name": "demo", "source_file": "", "steps": [
    {"id": 1, "title": "Name", "instruction": "Extract the name.", "output_format": "text",
     "expected_output": "a name", "depends_on": []},
    {"id": 2, "title": "Class", "instruction": "Classify.",
     "output_format": "one_of:billing|technical", "expected_output": "one word",
     "depends_on": [1]}]}


def fake_api(monkeypatch, class_answers):
    answers = iter(class_answers)

    def gen(prompt, model):
        if "Does the output follow" in prompt:
            return "PASS"
        return next(answers) if "Step 2:" in prompt.split("Original input")[0] else "Ravi"

    monkeypatch.setattr(llm, "_generate", gen)


def test_events_in_order_with_a_repair(monkeypatch):
    fake_api(monkeypatch, ["It looks like billing", "billing"])
    seen = []
    trace = run_skill("", "in", plan=PLAN, model="m", on_event=seen.append)
    kinds = [(e["type"], e.get("step_id"), e.get("attempt")) for e in seen]
    assert kinds == [
        ("run_start", None, None), ("plan", None, None),
        ("step_start", 1, None), ("attempt_start", 1, 1), ("attempt_end", 1, 1), ("step_end", 1, None),
        ("step_start", 2, None), ("attempt_start", 2, 1), ("attempt_end", 2, 1),
        ("attempt_start", 2, 2), ("attempt_end", 2, 2), ("step_end", 2, None),
        ("run_end", None, None)]
    first, second = [e for e in seen if e["type"] == "attempt_end" and e["step_id"] == 2]
    assert first["ok"] is False and "Expected exactly one of" in first["checker_note"]
    assert second["ok"] is True and second["output"] == "billing"
    assert [e for e in seen if e["type"] == "step_end"][1]["status"] == "repaired"
    assert seen[-1]["trace"] == trace
    assert seen[1]["steps"] == [{"id": 1, "title": "Name"}, {"id": 2, "title": "Class"}]
    json.dumps(seen)  # every event is plain JSON


def test_run_start_says_whether_it_will_split(monkeypatch):
    fake_api(monkeypatch, ["billing"])
    seen = []
    run_skill("", "in", plan=PLAN, model="m", on_event=seen.append)
    assert seen[0] == {"type": "run_start", "will_split": False, "mode": "full"}


def test_a_broken_listener_does_not_break_the_run(monkeypatch):
    fake_api(monkeypatch, ["billing"])

    def boom(event):
        raise RuntimeError("listener bug")

    trace = run_skill("", "in", plan=PLAN, model="m", on_event=boom)
    assert [s["status"] for s in trace["steps"]] == ["pass", "pass"]


def test_no_listener_changes_nothing(monkeypatch):
    fake_api(monkeypatch, ["billing"])
    assert run_skill("", "in", plan=PLAN, model="m")["final_output"] == "billing"


def test_ndjson_stream_ends_with_the_trace(monkeypatch):
    fake_api(monkeypatch, ["billing"])
    lines = list(ndjson_events("", "in", plan=PLAN, model="m"))
    events = [json.loads(l) for l in lines]
    assert all(l.endswith("\n") for l in lines)
    assert events[0]["type"] == "run_start" and events[-1]["type"] == "run_end"
    assert events[-1]["trace"]["final_output"] == "billing"


def test_ndjson_reports_a_crash_as_an_error_event(monkeypatch):
    def broken(*a, **k):
        raise ValueError("bad skill")

    monkeypatch.setattr(runner, "run_skill", broken)
    events = [json.loads(l) for l in ndjson_events("", "in")]
    assert events == [{"type": "error", "message": "ValueError: bad skill"}]


def test_closing_the_stream_stops_the_run(monkeypatch):
    calls = []

    def slow(prompt, model):
        calls.append(prompt)
        time.sleep(0.05)
        return "PASS" if "Does the output follow" in prompt else "x"

    monkeypatch.setattr(llm, "_generate", slow)
    many = {"skill_name": "s", "source_file": "", "steps": [
        {"id": i, "title": f"S{i}", "instruction": "do", "output_format": "text",
         "expected_output": "", "depends_on": []} for i in range(1, 41)]}
    stream = ndjson_events("", "in", plan=many, model="m")
    next(stream)                 # run_start
    next(stream)                 # plan
    stream.close()               # the browser went away
    time.sleep(0.5)
    settled = len(calls)
    time.sleep(0.4)
    assert len(calls) == settled < 20  # stopped early, and nothing more is called
