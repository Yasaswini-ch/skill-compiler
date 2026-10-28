"""Tests for web/doctor.py with fake model calls: no API key, no network."""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "web"))

import doctor  # noqa: E402

SKILL = "---\nname: demo\n---\n1. Say the name.\n2. Say the city in at most 5 words.\n3. Output JSON with keys name, city."


@pytest.fixture
def client():
    import server
    return server.app.test_client()


# ------------------------------------------------------------------ the check builder

def test_build_checks_from_the_form():
    checks = doctor.build_checks({"max_words": "20", "starts_with": "Hi ", "contains": "refund", "json_keys": "name, city"})
    assert [c["type"] for c in checks] == ["max_words", "starts_with", "contains", "json_valid", "json_keys"]
    assert checks[0]["value"] == 20 and checks[-1]["value"] == ["name", "city"]
    assert [c["id"] for c in checks] == ["u1", "u2", "u3", "u4", "u5"]


@pytest.mark.parametrize("spec", [None, {}, "x", {"max_words": ""}, {"starts_with": "  "}, {"json_keys": ""}, {"json_keys": [" "]}])
def test_no_checks_means_no_scoring(spec):
    assert doctor.build_checks(spec) == []


@pytest.mark.parametrize("spec", [{"max_words": "many"}, {"max_words": 0.5}, {"max_words": 5000}, {"contains": "x" * 201}])
def test_bad_checks_are_rejected(spec):
    with pytest.raises(doctor.BadRequest):
        doctor.build_checks(spec)


def test_checks_are_described_in_plain_words():
    assert doctor.describe({"type": "max_words", "value": 20}) == "at most 20 words"
    assert doctor.describe({"type": "json_keys", "value": ["a", "b"]}) == "has the JSON keys a, b"


# ------------------------------------------------------------------ routes

def test_requests_without_a_skill_or_with_a_huge_one_are_rejected(client):
    for route in ("compile", "rewrite", "try"):
        assert client.post(f"/doctor/{route}", json={}).status_code == 400
        assert client.post(f"/doctor/{route}", json={"skill_text": "   "}).status_code == 400
        big = client.post(f"/doctor/{route}", json={"skill_text": "x" * (doctor.MAX_SKILL + 1)})
        assert big.status_code == 400 and "limit is 6000" in big.get_json()["error"]
    assert client.post("/doctor/compile", data="not json", content_type="application/json").status_code == 400


def test_compile_shows_the_steps_and_says_nothing_is_scored(client, monkeypatch):
    plan = {"skill_name": "demo", "warnings": ["w"], "steps": [
        {"id": 1, "title": "Name", "instruction": "Say the name.", "output_format": "text", "expected_output": "", "depends_on": []}]}
    monkeypatch.setattr(doctor, "_compile", lambda skill: plan)
    data = client.post("/doctor/compile", json={"skill_text": SKILL}).get_json()
    assert data["steps"][0]["title"] == "Name" and data["warnings"] == ["w"]
    assert data["unverified"] is True and "Nothing here is scored" in data["note"]


def test_rewrite_reports_lint_before_after_and_lost_constraints(client, monkeypatch):
    class FakeLLM:
        @staticmethod
        def call_llm(prompt):
            assert SKILL in prompt                                    # the original goes into the rewrite prompt
            return "```\n---\nname: demo\n---\n1. Say the name.\n2. Say the city.\n3. Output JSON.\n```"

    monkeypatch.setattr(doctor, "_llm", FakeLLM)
    monkeypatch.setattr(doctor, "_lint", lambda text: {"score": 10 if "at most 5" in text else 3, "level": "low", "steps": 3, "findings": []})
    data = client.post("/doctor/rewrite", json={"skill_text": SKILL}).get_json()
    assert data["rewritten"].startswith("---\nname: demo") and "```" not in data["rewritten"]
    assert (data["lint_before"]["score"], data["lint_after"]["score"]) == (10, 3)
    assert "number 5" in data["lost"] and "Do not trust it" in data["note"]      # the "at most 5 words" limit was dropped
    assert data["unverified"] is True


def test_rewrite_that_keeps_everything_says_so(client, monkeypatch):
    class FakeLLM:
        @staticmethod
        def call_llm(prompt):
            return SKILL

    monkeypatch.setattr(doctor, "_llm", FakeLLM)
    monkeypatch.setattr(doctor, "_lint", lambda text: {"score": 5, "level": "low", "steps": 3, "findings": []})
    data = client.post("/doctor/rewrite", json={"skill_text": SKILL}).get_json()
    assert data["lost"] == [] and "risk estimate, not a measured pass rate" in data["note"]


def fake_runners(monkeypatch, plain_out, harness_out):
    monkeypatch.setattr(doctor, "_run_plain", lambda skill, text: {"final_output": plain_out})
    monkeypatch.setattr(doctor, "_run_skill", lambda skill, text, mode=None: {"final_output": harness_out, "totals": {"llm_calls": 9}})
    monkeypatch.setattr(doctor, "_score", lambda task, out: {
        "passed": all(c["value"] in out for c in task["checks"] if c["type"] == "contains"),
        "failed_checks": [c["id"] for c in task["checks"] if c["type"] == "contains" and c["value"] not in out],
        "details": {c["id"]: f"missing {c['value']}" for c in task["checks"] if c["type"] == "contains" and c["value"] not in out}})


def test_try_scores_both_sides_with_the_users_checks(client, monkeypatch):
    fake_runners(monkeypatch, "no refund here", "a refund is on its way")
    data = client.post("/doctor/try", json={"skill_text": SKILL, "input": "x", "checks": {"contains": "on its way"}}).get_json()
    assert data["checks"] == ['contains "on its way"']
    assert data["plain"]["passed"] is False and data["plain"]["failed"][0]["check"] == 'contains "on its way"'
    assert data["harness"]["passed"] is True and data["harness"]["model_calls"] == 9
    assert data["one_run"] is True and "one run each" in data["note"]


def test_try_without_checks_refuses_to_score(client, monkeypatch):
    fake_runners(monkeypatch, "a", "b")
    reply = client.post("/doctor/try", json={"skill_text": SKILL, "input": "x", "checks": {}})
    assert reply.status_code == 400 and "Without checks nothing can be scored" in reply.get_json()["error"]


def test_try_input_rules(client, monkeypatch):
    fake_runners(monkeypatch, "a", "b")
    body = {"skill_text": SKILL, "checks": {"contains": "a"}}
    assert client.post("/doctor/try", json={**body, "input": ""}).status_code == 400
    assert client.post("/doctor/try", json={**body, "input": "x" * 1501}).status_code == 400


def test_a_second_request_while_busy_gets_429_not_a_queue(client, monkeypatch):
    monkeypatch.setattr(doctor, "_compile", lambda skill: {"skill_name": "d", "steps": []})
    assert doctor.BUSY.acquire(blocking=False)
    try:
        reply = client.post("/doctor/compile", json={"skill_text": SKILL})
        assert reply.status_code == 429 and "Try again" in reply.get_json()["error"]
    finally:
        doctor.BUSY.release()
    assert client.post("/doctor/compile", json={"skill_text": SKILL}).status_code == 200   # and it is released afterwards


def test_a_model_error_is_a_502_and_releases_the_lock(client, monkeypatch):
    def boom(skill):
        raise RuntimeError("503 UNAVAILABLE")

    monkeypatch.setattr(doctor, "_compile", boom)
    reply = client.post("/doctor/compile", json={"skill_text": SKILL})
    assert reply.status_code == 502 and "503" in reply.get_json()["error"]
    assert doctor.BUSY.acquire(blocking=False)
    doctor.BUSY.release()


def test_a_missing_piece_is_a_501(client, monkeypatch):
    monkeypatch.setattr(doctor, "_compile", None)
    assert client.post("/doctor/compile", json={"skill_text": SKILL}).status_code == 501


def test_every_check_type_works_with_the_real_scorer():
    """describe() and the scorer must accept every check the form can build (a word limit once crashed describe)."""
    scorer = pytest.importorskip("benchmark.scorer")
    spec = {"max_words": 5, "starts_with": "Hi", "contains": "refund", "json_keys": "a, b"}
    checks = doctor.build_checks(spec)
    assert len(checks) == 5 and all(doctor.describe(c) for c in checks)
    good = '{"a": 1, "b": 2}'
    # a JSON answer cannot also start with "Hi", so score each kind on its own as well
    for check, ok, bad in [({"max_words": 3}, "one two", "one two three four"), ({"starts_with": "Hi"}, "Hi there", "Hello"),
                           ({"contains": "refund"}, "a refund", "nothing"), ({"json_keys": "a, b"}, good, '{"a": 1}')]:
        built = doctor.build_checks(check)
        monkey_score = lambda out, built=built: scorer.score_output({"checks": built}, out)
        assert monkey_score(ok)["passed"] is True, (check, ok)
        assert monkey_score(bad)["passed"] is False, (check, bad)
    assert doctor._score is scorer.score_output  # score_side uses the real scorer unless a test replaced it
    side = doctor.score_side(checks, "Hello, a refund")
    assert side["passed"] is False and {f["check"] for f in side["failed"]} >= {'starts with "Hi"', "is valid JSON"}
    assert all(f["reason"] for f in side["failed"])
