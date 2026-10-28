import json
import time

import pytest

from skillcompiler import llm
from skillcompiler.stream import ndjson_events


def step(i, instruction="do it", **kw):
    return {"id": i, "title": f"S{i}", "instruction": instruction, "output_format": "text",
            "expected_output": "", "depends_on": [], **kw}


def plan_of(n):
    return {"skill_name": "s", "source_file": "", "steps": [step(i) for i in range(1, n + 1)]}


def collect(stream):
    return [json.loads(line) for line in stream]


def fake_ok(monkeypatch, delay=0.0):
    calls = []

    def gen(prompt, model):
        calls.append(prompt)
        if delay:
            time.sleep(delay)
        return "PASS" if "Does the output follow" in prompt else "x"

    monkeypatch.setattr(llm, "_generate", gen)
    return calls


def errors(events):
    return [e for e in events if e["type"] == "error"]


def test_a_normal_run_has_no_error(monkeypatch):
    fake_ok(monkeypatch)
    events = collect(ndjson_events("", "in", plan=plan_of(2), model="m"))
    assert events[-1]["type"] == "run_end" and not errors(events)


def test_too_many_steps_stops_before_any_step_runs(monkeypatch):
    calls = fake_ok(monkeypatch)
    events = collect(ndjson_events("", "in", plan=plan_of(8), model="m", max_steps=6))
    kinds = [e["type"] for e in events]
    assert kinds == ["run_start", "plan", "error"]            # the plan is shown, then one error
    assert "8 steps" in events[-1]["message"] and "limit here is 6" in events[-1]["message"]
    assert calls == []                                          # nothing was spent


def test_within_the_step_limit_runs_normally(monkeypatch):
    fake_ok(monkeypatch)
    events = collect(ndjson_events("", "in", plan=plan_of(6), model="m", max_steps=6))
    assert events[-1]["type"] == "run_end"


def test_empty_plan_is_one_error(monkeypatch):
    fake_ok(monkeypatch)
    events = collect(ndjson_events("", "in", plan={"skill_name": "s", "source_file": "", "steps": []}, model="m"))
    assert len(errors(events)) == 1 and events[-1]["type"] == "error"


def test_timeout_sends_one_error_and_the_run_stops_spending(monkeypatch):
    calls = fake_ok(monkeypatch, delay=0.15)
    started = time.monotonic()
    events = collect(ndjson_events("", "in", plan=plan_of(30), model="m", timeout_s=0.5))
    assert time.monotonic() - started < 3
    assert len(errors(events)) == 1 and "longer than 0.5 s" in events[-1]["message"]
    time.sleep(0.6)                                             # let an in-flight call finish
    settled = len(calls)
    time.sleep(0.5)
    assert len(calls) == settled < 20                           # and then nothing more is called


def test_one_hanging_call_still_ends_the_stream_at_the_deadline(monkeypatch):
    def hang(prompt, model):
        time.sleep(2.0)                                         # a stalled connection
        return "x"

    monkeypatch.setattr(llm, "_generate", hang)
    started = time.monotonic()
    events = collect(ndjson_events("", "in", plan=plan_of(2), model="m", timeout_s=0.4))
    assert time.monotonic() - started < 1.5                     # did not wait for the hung call
    assert events[-1]["type"] == "error" and len(errors(events)) == 1


def test_a_failing_model_api_stops_after_three_calls_with_one_error(monkeypatch):
    attempts = []

    def broken(prompt, model):
        attempts.append(1)
        raise RuntimeError("503 UNAVAILABLE")

    monkeypatch.setattr(llm, "_generate", broken)
    monkeypatch.setattr(llm.time, "sleep", lambda s: None)
    events = collect(ndjson_events("", "in", plan=plan_of(5), model="m"))
    assert len(errors(events)) == 1 and events[-1]["type"] == "error"
    assert "3 calls in a row" in events[-1]["message"] and "503" in events[-1]["message"]
    before = len(attempts)
    time.sleep(0.3)
    assert len(attempts) == before                              # no more calls after the error
    assert sum(1 for e in events if e["type"] == "attempt_end") == 3


def test_a_missing_api_key_is_one_clear_error_and_no_retry_delay(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setattr(llm, "_client", None)
    slept = []
    monkeypatch.setattr(llm.time, "sleep", slept.append)
    events = collect(ndjson_events("", "in", plan=plan_of(3), model="m"))
    assert len(errors(events)) == 1 and "GEMINI_API_KEY is not set" in events[-1]["message"]
    assert slept == []                                          # a config error is not retried


def test_a_crash_inside_the_run_becomes_one_error_not_an_exception():
    events = collect(ndjson_events("", "in", plan="not a plan", model="m"))
    assert len(errors(events)) == 1 and events[-1]["type"] == "error"


def test_unknown_mode_is_one_error():
    events = collect(ndjson_events("", "in", plan=plan_of(1), model="m", mode="turbo"))
    assert len(errors(events)) == 1 and "unknown mode" in events[-1]["message"]


def test_verify_and_mode_are_passed_through(monkeypatch):
    calls = fake_ok(monkeypatch)
    events = collect(ndjson_events("", "in", plan=plan_of(2), model="m", verify=False, mode="adaptive"))
    assert events[0]["mode"] == "adaptive"
    assert not any("Does the output follow" in c for c in calls)
    assert events[-1]["trace"]["mode_detail"]["verified_steps"] == []
    assert all(e["verified"] is False for e in events if e["type"] == "step_end")


def test_closing_the_stream_stops_the_run_and_drops_queued_events(monkeypatch):
    calls = fake_ok(monkeypatch, delay=0.05)
    stream = ndjson_events("", "in", plan=plan_of(40), model="m")
    next(stream)
    next(stream)
    stream.close()
    time.sleep(0.4)
    settled = len(calls)
    time.sleep(0.4)
    assert len(calls) == settled < 30


def test_the_generator_does_not_raise_when_the_consumer_is_slow(monkeypatch):
    fake_ok(monkeypatch)
    lines = []
    for line in ndjson_events("", "in", plan=plan_of(2), model="m", timeout_s=30):
        time.sleep(0.01)
        lines.append(line)
    assert json.loads(lines[-1])["type"] == "run_end"
