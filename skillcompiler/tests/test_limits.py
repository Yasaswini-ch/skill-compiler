import pytest

from skillcompiler import llm, run_skill


class Clock:
    def __init__(self):
        self.t = 0.0
        self.slept = []

    def now(self):
        return self.t

    def sleep(self, s):
        self.slept.append(s)
        self.t += s


def test_limiter_allows_rpm_then_waits():
    clock = Clock()
    limiter = llm.RateLimiter(now=clock.now, sleep=clock.sleep)
    for _ in range(3):
        limiter.wait(3)
    assert clock.slept == []          # first 3 go straight through
    limiter.wait(3)                   # the 4th must wait for the window to clear
    assert clock.slept and abs(sum(clock.slept) - 60) < 1


def test_limiter_off_when_zero():
    clock = Clock()
    limiter = llm.RateLimiter(now=clock.now, sleep=clock.sleep)
    for _ in range(100):
        limiter.wait(0)
    assert clock.slept == []


def test_rpm_env(monkeypatch):
    monkeypatch.setenv("GEMMA_RPM", "7")
    assert llm._rpm() == 7
    monkeypatch.setenv("GEMMA_RPM", "junk")
    assert llm._rpm() == 25


def test_retry_delay_reads_the_servers_hint():
    msg = "429 RESOURCE_EXHAUSTED ... Please retry in 48.9s. ... 'retryDelay': '48s'"
    assert llm._retry_delay(RuntimeError(msg), 0) == pytest.approx(49.9)
    assert llm._retry_delay(RuntimeError("500 INTERNAL"), 1) == 2      # plain backoff
    assert llm._retry_delay(RuntimeError("retry in 500s"), 0) == 70    # capped


def test_call_llm_sleeps_for_the_hint_then_succeeds(monkeypatch):
    slept = []
    monkeypatch.setattr(llm.time, "sleep", slept.append)
    answers = iter([RuntimeError("429 ... retry in 10s"), "ok"])

    def fake(prompt, model):
        a = next(answers)
        if isinstance(a, Exception):
            raise a
        return a

    monkeypatch.setattr(llm, "_generate", fake)
    assert llm.call_llm("p", model="m") == "ok"
    assert slept == [11.0]


STEP_PLAN = {"skill_name": "s", "source_file": "", "steps": [
    {"id": 1, "title": "Sum", "instruction": "Add the numbers.", "output_format": "text",
     "expected_output": "a number", "depends_on": []}]}


def test_repeated_answer_overrules_verifier(monkeypatch):
    """A verifier that keeps rejecting an unchanged answer must not drag the model off it."""
    def fake(prompt, model):
        return "FAIL: wrong sum" if "Does the output follow" in prompt else "20.00"

    monkeypatch.setattr(llm, "_generate", fake)
    t = run_skill("", "x", plan=STEP_PLAN, model="m")
    step = t["steps"][0]
    assert step["status"] == "repaired" and len(step["attempts"]) == 2
    assert "overruled" in step["attempts"][1]["checker_note"]
    assert t["final_output"] == "20.00"


def test_changed_answer_is_still_rejected(monkeypatch):
    answers = iter(["19", "21", "22"])

    def fake(prompt, model):
        return "FAIL: wrong" if "Does the output follow" in prompt else next(answers)

    monkeypatch.setattr(llm, "_generate", fake)
    t = run_skill("", "x", plan=STEP_PLAN, model="m")
    assert t["steps"][0]["status"] == "fail" and len(t["steps"][0]["attempts"]) == 3


def test_flip_flop_is_not_overruled_it_stays_a_failure(monkeypatch):
    """travel -> other -> travel: the model dropped an answer and came back to it. The verifier's
    objections stand (benchmark t04: it was right), so the step fails instead of 'repairing'."""
    answers = iter(["travel", "other", "travel"])

    def fake(prompt, model):
        return "FAIL: no" if "Does the output follow" in prompt else next(answers)

    monkeypatch.setattr(llm, "_generate", fake)
    t = run_skill("", "x", plan=STEP_PLAN, model="m")
    assert t["steps"][0]["status"] == "fail" and len(t["steps"][0]["attempts"]) == 3
    assert not any("overruled" in a["checker_note"] for a in t["steps"][0]["attempts"])


def test_verifier_switch_by_environment(monkeypatch):
    calls = []

    def fake(prompt, model):
        calls.append(prompt)
        return "PASS" if "Does the output follow" in prompt else "20"

    monkeypatch.setattr(llm, "_generate", fake)
    monkeypatch.setenv("SKILLCOMPILER_VERIFY", "0")
    t = run_skill("", "x", plan=STEP_PLAN, model="m")
    assert t["totals"]["llm_calls"] == 1                      # answer only, no verification
    monkeypatch.delenv("SKILLCOMPILER_VERIFY")
    assert run_skill("", "x", plan=STEP_PLAN, model="m")["totals"]["llm_calls"] == 2
    monkeypatch.setenv("SKILLCOMPILER_VERIFY", "0")
    assert run_skill("", "x", plan=STEP_PLAN, model="m", verify=True)["totals"]["llm_calls"] == 2


JSON_STEP = {"id": 8, "title": "Format", "instruction": "Output JSON.", "output_format": "json",
             "expected_output": "", "depends_on": [5]}
EARLIER = "\nResults of earlier steps:\nStep 5 (Check): no\n"


def test_json_assembly_step_is_told_to_copy_results_verbatim_when_enabled(monkeypatch):
    from skillcompiler.runner import COPY_RULE, build_prompt
    monkeypatch.setenv("SKILLCOMPILER_COPY_RULE", "1")
    prompt = build_prompt(JSON_STEP, "input", EARLIER)
    assert COPY_RULE in prompt and "not true or false" in prompt
    # ... and only there: no earlier results, or not a JSON step, leaves the prompt as it was
    assert COPY_RULE not in build_prompt({**JSON_STEP, "depends_on": []}, "input", "")
    assert COPY_RULE not in build_prompt({**JSON_STEP, "output_format": "text"}, "input", EARLIER)


def test_copy_rule_is_off_by_default(monkeypatch):
    from skillcompiler.runner import COPY_RULE, build_prompt
    monkeypatch.delenv("SKILLCOMPILER_COPY_RULE", raising=False)
    assert COPY_RULE not in build_prompt(JSON_STEP, "input", EARLIER)


@pytest.mark.parametrize("env,expected_ms", [(None, 240000), ("7", 7000), ("0.5", 500)])
def test_client_gets_a_request_timeout(monkeypatch, env, expected_ms):
    import google.genai as genai

    seen = {}

    class FakeClient:
        def __init__(self, **kwargs):
            seen.update(kwargs)

    monkeypatch.setattr(genai, "Client", FakeClient)
    monkeypatch.setattr(llm, "_client", None)
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    if env is None:
        monkeypatch.delenv("GEMMA_TIMEOUT", raising=False)
    else:
        monkeypatch.setenv("GEMMA_TIMEOUT", env)
    llm._get_client()
    assert seen["http_options"].timeout == expected_ms
    monkeypatch.setattr(llm, "_client", None)  # do not leak the fake client
