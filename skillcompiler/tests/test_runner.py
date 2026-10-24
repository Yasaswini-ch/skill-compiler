import json

import pytest

from skillcompiler import llm, run_skill

PLAN = {"skill_name": "demo", "source_file": "", "steps": [
    {"id": 1, "title": "Name", "instruction": "Extract the name.", "output_format": "text",
     "expected_output": "a name", "depends_on": []},
    {"id": 2, "title": "Class", "instruction": "Classify.",
     "output_format": "one_of:billing|technical", "expected_output": "one word",
     "depends_on": [1]},
    {"id": 3, "title": "Final", "instruction": "Output JSON.", "output_format": "json",
     "expected_output": "json", "depends_on": [1, 2]},
]}


def script(monkeypatch, step_replies, verdict="PASS: ok"):
    """Fake the raw API. step_replies maps 'Step N' -> list of replies in order."""
    prompts = []

    def fake(prompt, model):
        prompts.append(prompt)
        if "Does the output follow" in prompt:
            return verdict
        for key, replies in step_replies.items():
            if f"Step {key}:" in prompt.split("Original input")[0]:
                return replies.pop(0)
        raise AssertionError("unexpected prompt: " + prompt[:80])

    monkeypatch.setattr(llm, "_generate", fake)
    monkeypatch.setattr(llm.time, "sleep", lambda s: None)
    return prompts


def test_clean_run(monkeypatch):
    script(monkeypatch, {1: ["Ravi"], 2: ["billing"], 3: ['{"name": "Ravi"}']})
    t = run_skill("", "ticket", plan=PLAN, model="m")
    assert [s["status"] for s in t["steps"]] == ["pass"] * 3
    assert t["mode"] == "harness" and t["mock"] is False
    assert t["final_output"] == '{"name": "Ravi"}'
    assert t["totals"] == {"llm_calls": 6, "latency_ms": t["totals"]["latency_ms"], "retries": 0, "cache_hits": 0}


def test_retry_with_feedback_then_repaired(monkeypatch):
    prompts = script(monkeypatch, {1: ["Ravi"], 2: ["It looks like billing", "billing"],
                                   3: ["{}"]})
    t = run_skill("", "ticket", plan=PLAN, model="m")
    step2 = t["steps"][1]
    assert step2["status"] == "repaired" and len(step2["attempts"]) == 2
    assert step2["attempts"][0]["format_ok"] is False
    assert t["totals"]["retries"] == 1
    retry_prompt = [p for p in prompts if "previous answer was rejected" in p][0]
    assert "It looks like billing" in retry_prompt and "Expected exactly one of" in retry_prompt


def test_failed_step_does_not_stop_run(monkeypatch):
    script(monkeypatch, {1: ["Ravi"], 2: ["bad", "bad", "bad"], 3: ["{}"]})
    t = run_skill("", "ticket", plan=PLAN, model="m")
    assert [s["status"] for s in t["steps"]] == ["pass", "fail", "pass"]
    assert len(t["steps"][1]["attempts"]) == 3
    assert t["final_output"] == "{}"


def test_earlier_outputs_are_passed_forward(monkeypatch):
    prompts = script(monkeypatch, {1: ["Ravi"], 2: ["billing"], 3: ["{}"]})
    run_skill("", "ticket text", plan=PLAN, model="m")
    last = [p for p in prompts if "Step 3:" in p.split("Original input")[0]][0]
    assert "Step 1 (Name): Ravi" in last and "Step 2 (Class): billing" in last
    assert "ticket text" in last


def test_api_failure_is_recorded_not_raised(monkeypatch):
    monkeypatch.setattr(llm.time, "sleep", lambda s: None)

    def boom(prompt, model):
        raise RuntimeError("500")

    monkeypatch.setattr(llm, "_generate", boom)
    t = run_skill("", "x", plan=PLAN, model="m", max_retries=0)
    assert [s["status"] for s in t["steps"]] == ["fail"] * 3
    assert "LLM call failed" in t["steps"][0]["attempts"][0]["checker_note"]


def test_trace_is_json_serializable_and_splits_when_no_plan(monkeypatch):
    plan_json = json.dumps({"steps": PLAN["steps"]})

    def fake(prompt, model):
        if "precise parser" in prompt:
            return plan_json
        if "Does the output follow" in prompt:
            return "PASS"
        return {"1": "Ravi", "2": "billing", "3": "{}"}[prompt.split("Step ")[1][0]]

    monkeypatch.setattr(llm, "_generate", fake)
    t = run_skill("1. a\n2. b\n3. c", "x", model="m")
    json.dumps(t)
    assert t["totals"]["llm_calls"] == 7  # 1 split + 3 steps + 3 verifications


def test_format_hint_is_plain_words():
    from skillcompiler.runner import format_hint
    assert "billing, technical" in format_hint("one_of:billing|technical")
    assert "one_of" not in format_hint("one_of:billing|technical")
    assert format_hint("max_words:60") == "at most 60 words"
    assert format_hint("weird") == "weird"
