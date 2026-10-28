import json

import pytest

from skillcompiler import __main__ as cli
from skillcompiler import llm, run_skill
from skillcompiler.runner import is_risky

PLAN = {"skill_name": "inv", "source_file": "", "steps": [
    {"id": 1, "title": "Vendor", "instruction": "Extract the vendor name.", "output_format": "text",
     "expected_output": "", "depends_on": []},
    {"id": 2, "title": "Note", "instruction": "Write a friendly sentence about the vendor.", "output_format": "text",
     "expected_output": "", "depends_on": [1]},
    {"id": 3, "title": "Total", "instruction": "Compute the total as price multiplied by quantity.",
     "output_format": "number", "expected_output": "", "depends_on": []},
    {"id": 4, "title": "Report", "instruction": "Write the report.", "output_format": "text",
     "expected_output": "", "depends_on": [1, 3]}]}


def step(**kw):
    base = {"id": 1, "title": "t", "instruction": "Do a thing.", "output_format": "text",
            "expected_output": "", "depends_on": []}
    return {**base, **kw}


@pytest.mark.parametrize("kw,risky", [
    ({}, False),
    ({"output_format": "json"}, True),
    ({"output_format": "one_of:a|b"}, True),
    ({"instruction": "Add the two prices."}, True),
    ({"instruction": "Take 10% off the subtotal."}, True),
    ({"instruction": "Work out 3 x 4."}, True),
    ({"instruction": "Reply in at most 20 words."}, True),
    ({"instruction": "It must begin with Hi."}, True),
    ({"instruction": "Never mention the price."}, True),
    ({"instruction": "Say hello warmly."}, False),
    ({"depends_on": [1]}, False),
    ({"depends_on": [1, 2]}, True),
])
def test_is_risky(kw, risky):
    plan = {"steps": [step(id=1), step(id=9)]}
    assert is_risky(step(**kw, id=5), plan) is risky


def test_the_final_step_is_always_risky():
    plan = {"steps": [step(id=1), step(id=2)]}
    assert is_risky(step(id=2), plan) and not is_risky(step(id=1), plan)


def fake_api(monkeypatch):
    calls = {"answer": 0, "verify": 0}

    def gen(prompt, model):
        if "Does the output follow" in prompt:
            calls["verify"] += 1
            return "PASS"
        calls["answer"] += 1
        return "12"

    monkeypatch.setattr(llm, "_generate", gen)
    return calls


def test_adaptive_makes_fewer_calls_than_full(monkeypatch):
    calls = fake_api(monkeypatch)
    full = run_skill("", "x", plan=PLAN, model="m", mode="full")
    full_calls = dict(calls)
    calls.update(answer=0, verify=0)
    adaptive = run_skill("", "x", plan=PLAN, model="m", mode="adaptive")
    assert full_calls == {"answer": 4, "verify": 4}                  # unchanged behaviour
    assert calls == {"answer": 4, "verify": 2}                       # only steps 3 and 4 are risky
    assert full["totals"]["llm_calls"] == 8 and adaptive["totals"]["llm_calls"] == 6


def test_adaptive_records_which_steps_were_verified(monkeypatch):
    fake_api(monkeypatch)
    trace = run_skill("", "x", plan=PLAN, model="m", mode="adaptive")
    assert trace["mode_detail"] == {"strategy": "adaptive", "route": "harness",
                                    "verified_steps": [3, 4], "skipped_verify_steps": [1, 2]}
    assert [s["status"] for s in trace["steps"]] == ["pass"] * 4


def test_full_mode_trace_is_unchanged(monkeypatch):
    fake_api(monkeypatch)
    trace = run_skill("", "x", plan=PLAN, model="m")
    assert "mode_detail" not in trace
    assert set(trace) == {"run_id", "mode", "mock", "model", "skill", "input", "steps", "final_output", "totals"}


def test_adaptive_still_runs_the_format_check_on_skipped_steps(monkeypatch):
    """A step the verifier skips is still checked for format and rules, and still retried."""
    plan = {"skill_name": "s", "source_file": "", "steps": [
        {"id": 1, "title": "Short", "instruction": "Say hi.", "output_format": "text", "expected_output": "",
         "depends_on": []},
        {"id": 2, "title": "End", "instruction": "Say bye.", "output_format": "text", "expected_output": "",
         "depends_on": [1]}]}
    answers = iter(["", "hi", "bye"])     # step 1 first answers with nothing: the format check rejects it

    def gen(prompt, model):
        return "PASS" if "Does the output follow" in prompt else next(answers)

    monkeypatch.setattr(llm, "_generate", gen)
    trace = run_skill("", "x", plan=plan, model="m", mode="adaptive")
    assert trace["steps"][0]["status"] == "repaired" and trace["steps"][0]["attempts"][0]["format_ok"] is False
    assert 1 in trace["mode_detail"]["skipped_verify_steps"]


def test_verify_false_wins_over_adaptive(monkeypatch):
    calls = fake_api(monkeypatch)
    trace = run_skill("", "x", plan=PLAN, model="m", mode="adaptive", verify=False)
    assert calls["verify"] == 0
    assert trace["mode_detail"]["verified_steps"] == [] and trace["mode_detail"]["skipped_verify_steps"] == [1, 2, 3, 4]


def test_mode_from_environment_and_explicit_argument_wins(monkeypatch):
    fake_api(monkeypatch)
    monkeypatch.setenv("SKILLCOMPILER_MODE", "adaptive")
    assert "mode_detail" in run_skill("", "x", plan=PLAN, model="m")
    assert "mode_detail" not in run_skill("", "x", plan=PLAN, model="m", mode="full")


def test_unknown_mode_is_rejected():
    with pytest.raises(ValueError, match="unknown mode"):
        run_skill("", "x", plan=PLAN, model="m", mode="turbo")


def test_cli_mode_flag(monkeypatch, tmp_path, capsys):
    fake_api(monkeypatch)
    skill = tmp_path / "SKILL.md"
    skill.write_text("1. a\n", encoding="utf-8")
    plan = tmp_path / "plan.json"
    plan.write_text(json.dumps(PLAN), encoding="utf-8")
    trace = tmp_path / "trace.json"
    code = cli.main(["run", str(skill), "--input", "x", "--plan", str(plan), "--model", "m",
                     "--mode", "adaptive", "--trace", str(trace)])
    assert code == 0
    assert json.loads(trace.read_text(encoding="utf-8"))["mode_detail"]["strategy"] == "adaptive"


def test_events_carry_mode_and_verified(monkeypatch):
    fake_api(monkeypatch)
    seen = []
    run_skill("", "x", plan=PLAN, model="m", mode="adaptive", on_event=seen.append)
    assert seen[0]["mode"] == "adaptive"
    assert [e["verified"] for e in seen if e["type"] == "step_end"] == [False, False, True, True]
