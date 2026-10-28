import json

import pytest

from skillcompiler import __main__ as cli
from skillcompiler import llm, run_skill, runner
from skillcompiler.stream import ndjson_events

LOW = {"score": 5, "level": "low", "steps": 3, "findings": []}
HIGH = {"score": 70, "level": "high", "steps": 3, "findings": []}
JSON_SKILL = "---\nname: easy\n---\n1. Say the name.\n2. Say the city.\n3. Output JSON with keys name, city.\n"
TEXT_SKILL = "---\nname: easy\n---\n1. Say the name.\n2. Say the city.\n3. Write one friendly sentence.\n"

PLAN = {"skill_name": "p", "source_file": "", "steps": [
    {"id": 1, "title": "Name", "instruction": "Extract the name.", "output_format": "text",
     "expected_output": "", "depends_on": []},
    {"id": 2, "title": "Class", "instruction": "Classify.", "output_format": "one_of:billing|technical",
     "expected_output": "", "depends_on": [1]}]}


def lint_says(monkeypatch, report):
    monkeypatch.setattr(runner, "_lint_report", lambda text: report)


def fake_api(monkeypatch, answers):
    """answers: list consumed by non-verifier calls; each call is recorded as (model, kind)."""
    it = iter(answers)
    seen = []

    def gen(prompt, model):
        if "Does the output follow" in prompt:
            seen.append((model, "verify"))
            return "PASS"
        seen.append((model, "answer"))
        return next(it)

    monkeypatch.setattr(llm, "_generate", gen)
    return seen


# ---------------------------------------------------------------- auto mode

def test_easy_skill_runs_plain_in_one_call(monkeypatch):
    lint_says(monkeypatch, LOW)
    seen = fake_api(monkeypatch, ["Ravi lives in Pune."])
    events = []
    trace = run_skill(TEXT_SKILL, "Ravi, Pune", model="m", mode="auto", on_event=events.append)
    assert len(seen) == 1 and trace["totals"]["llm_calls"] == 1
    assert trace["mode"] == "plain" and trace["steps"] == [] and trace["final_output"] == "Ravi lives in Pune."
    assert trace["mode_detail"]["strategy"] == "auto" and trace["mode_detail"]["route"] == "plain"
    assert "lint score 5 (low), 3 steps" in trace["mode_detail"]["reason"]
    assert [e["type"] for e in events] == ["run_start", "route", "run_end"]   # no plan, no steps
    assert events[1] == {"type": "route", "route": "plain", "reason": trace["mode_detail"]["reason"]}


def test_plain_route_retries_once_when_the_json_is_bad(monkeypatch):
    lint_says(monkeypatch, LOW)
    seen = fake_api(monkeypatch, ["not json", '{"name": "Ravi", "city": "Pune"}'])
    trace = run_skill(JSON_SKILL, "Ravi, Pune", model="m", mode="auto")
    assert len(seen) == 2 and trace["totals"]["retries"] == 1
    assert trace["final_output"].startswith("{") and trace["mode_detail"]["final_check"]["ok"] is True


def test_plain_route_reports_a_failed_final_check_instead_of_hiding_it(monkeypatch):
    lint_says(monkeypatch, LOW)
    fake_api(monkeypatch, ["nope", "still nope"])
    trace = run_skill(JSON_SKILL, "x", model="m", mode="auto")
    assert trace["totals"]["llm_calls"] == 2                       # one retry, then it stops
    check = trace["mode_detail"]["final_check"]
    assert check["ok"] is False and "not valid JSON" in check["note"]


def test_risky_skill_gets_the_harness_in_adaptive_mode(monkeypatch):
    lint_says(monkeypatch, HIGH)
    fake_api(monkeypatch, ["Ravi", "billing"] * 3)
    events = []
    trace = run_skill(TEXT_SKILL, "x", plan=PLAN, model="m", mode="auto", on_event=events.append)
    assert trace["mode"] == "harness" and len(trace["steps"]) == 2
    detail = trace["mode_detail"]
    assert detail["strategy"] == "auto" and detail["route"] == "harness" and "high" in detail["reason"]
    assert detail["skipped_verify_steps"] == [1] and detail["verified_steps"] == [2]   # adaptive inside
    assert [e["type"] for e in events][:3] == ["run_start", "route", "plan"]


def test_a_long_skill_is_not_run_plain_even_if_the_linter_is_calm(monkeypatch):
    lint_says(monkeypatch, {**LOW, "steps": runner.AUTO_MAX_STEPS + 1})
    assert runner.choose_route("x")[0] == "harness"
    lint_says(monkeypatch, {**LOW, "steps": runner.AUTO_MAX_STEPS})
    assert runner.choose_route("x")[0] == "plain"
    lint_says(monkeypatch, {**LOW, "steps": 0})
    assert runner.choose_route("x")[0] == "harness"               # nothing parsed: do not guess


def test_without_the_linter_auto_falls_back_to_the_harness(monkeypatch):
    lint_says(monkeypatch, None)
    assert runner.choose_route("x") == ("harness", "linter not available")


def test_auto_through_the_stream_has_no_error(monkeypatch):
    lint_says(monkeypatch, LOW)
    fake_api(monkeypatch, ["a sentence"])
    events = [json.loads(l) for l in ndjson_events(TEXT_SKILL, "x", model="m", mode="auto", max_steps=6)]
    assert [e["type"] for e in events] == ["run_start", "route", "run_end"]


def test_the_real_linter_is_used_when_available():
    pytest.importorskip("tools.lint_skill")
    route, reason = runner.choose_route("---\nname: x\n---\n1. Do a thing.\n2. Do another.\n3. Output JSON with key a.\n")
    assert route in ("plain", "harness") and "lint score" in reason


def test_cli_accepts_auto_and_escalate_flags(monkeypatch, tmp_path):
    lint_says(monkeypatch, LOW)
    fake_api(monkeypatch, ["done"])
    skill = tmp_path / "SKILL.md"
    skill.write_text(TEXT_SKILL, encoding="utf-8")
    trace = tmp_path / "t.json"
    code = cli.main(["run", str(skill), "--input", "x", "--model", "m", "--mode", "auto",
                     "--escalate-model", "big", "--trace", str(trace)])
    assert code == 0 and json.loads(trace.read_text(encoding="utf-8"))["mode"] == "plain"


# ------------------------------------------------------------- escalation

def two_model_api(monkeypatch, small_answers, big_answers):
    smalls, bigs, seen = iter(small_answers), iter(big_answers), []

    def gen(prompt, model):
        if "Does the output follow" in prompt:
            seen.append((model, "verify"))
            return "PASS"
        seen.append((model, "answer"))
        return next(bigs if model == "big" else smalls)

    monkeypatch.setattr(llm, "_generate", gen)
    return seen


def test_a_step_that_keeps_failing_is_sent_to_the_bigger_model(monkeypatch):
    seen = two_model_api(monkeypatch, ["Ravi", "maybe", "perhaps", "unsure"], ["billing"])
    events = []
    trace = run_skill("", "x", plan=PLAN, model="small", escalate_model="big", on_event=events.append)
    step2 = trace["steps"][1]
    assert step2["status"] == "repaired" and step2["escalated"] is True and len(step2["attempts"]) == 4
    assert step2["attempts"][-1]["model"] == "big" and step2["attempts"][-1]["output"] == "billing"
    assert "model" not in step2["attempts"][0]                      # only the escalated attempt names a model
    assert trace["escalated_steps"] == [2] and trace["final_output"] == "billing"
    assert [m for m, kind in seen if kind == "answer"].count("big") == 1
    starts = [e for e in events if e["type"] == "attempt_start" and e["step_id"] == 2]
    assert starts[-1]["attempt"] == 4 and starts[-1]["model"] == "big"


def test_escalation_that_also_fails_stays_a_failure(monkeypatch):
    two_model_api(monkeypatch, ["Ravi", "x", "y", "z"], ["still wrong"])
    trace = run_skill("", "x", plan=PLAN, model="small", escalate_model="big")
    assert trace["steps"][1]["status"] == "fail" and trace["steps"][1]["escalated"] is True
    assert trace["escalated_steps"] == [2]


def test_steps_that_pass_are_never_escalated(monkeypatch):
    seen = two_model_api(monkeypatch, ["Ravi", "billing"], [])
    trace = run_skill("", "x", plan=PLAN, model="small", escalate_model="big")
    assert trace["escalated_steps"] == [] and all(m == "small" for m, _ in seen)
    assert all("escalated" not in s for s in trace["steps"])


def test_without_the_option_traces_are_unchanged(monkeypatch):
    two_model_api(monkeypatch, ["Ravi", "billing"], [])
    trace = run_skill("", "x", plan=PLAN, model="small")
    assert "escalated_steps" not in trace


def test_escalating_to_the_same_model_does_nothing(monkeypatch):
    two_model_api(monkeypatch, ["Ravi", "x", "y", "z"], [])
    trace = run_skill("", "x", plan=PLAN, model="small", escalate_model="small")
    assert trace["steps"][1]["status"] == "fail" and len(trace["steps"][1]["attempts"]) == 3
    assert trace["escalated_steps"] == []
