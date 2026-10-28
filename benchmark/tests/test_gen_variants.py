"""Tests for benchmark/gen_variants.py with a fake model. No API calls."""
import json

import pytest

from benchmark import gen_variants as gv
from benchmark.run_plain import load_tasks
from benchmark.scorer import score_output

TASKS = load_tasks()
SRC = TASKS[0]


def variant(**changes):
    v = {"title": "Harder", "input": "A new harder input about the same bug.",
         "difficulty_tags": ["similar_steps", "hard_limits"],
         "checks": [{"id": "c1", "type": "json_valid", "label": "wrong_format"},
                    {"id": "c2", "type": "json_keys", "value": ["a", "b"], "label": "skipped_step"},
                    {"id": "c3", "type": "max_words", "path": "a", "value": 10, "label": "ignored_constraint"},
                    {"id": "c4", "type": "regex", "path": "b", "value": "^x$", "label": "wrong_format"}]}
    v.update(changes)
    return v


def test_every_hand_written_task_passes_the_generated_task_schema():
    """The schema must accept the frozen tasks, otherwise it is stricter than the contract."""
    for t in TASKS:
        assert gv.validate_task(t, seen_inputs=set()) == [], t["task_id"]


def test_valid_variant_has_no_problems():
    assert gv.validate_task(variant(), SRC, set()) == []


@pytest.mark.parametrize("change,fragment", [
    ({"input": ""}, "missing input"),
    ({"input": SRC["input"]}, "identical to the source"),
    ({"title": " "}, "missing title"),
    ({"difficulty_tags": []}, "difficulty_tags"),
    ({"difficulty_tags": ["nonsense"]}, "difficulty_tags"),
    ({"skill_file": "skills/other/SKILL.md"}, "skill_file differs"),
    ({"extra": 1}, "unknown task keys"),
    ({"checks": variant()["checks"][:3]}, "4 to 7"),
    ({"checks": variant()["checks"] * 2}, "4 to 7"),
    ({"input": "x" * 2001}, "longer than"),
])
def test_task_level_problems(change, fragment):
    problems = gv.validate_task(variant(**change), SRC, set())
    assert any(fragment in p for p in problems), problems


def check(**kw):
    base = {"id": "c1", "type": "contains", "value": "x", "label": "other"}
    base.update(kw)
    return base


@pytest.mark.parametrize("bad", [
    check(type="nope"), check(label="made_up"), check(id=""), check(value=""), check(value=None),
    check(type="max_words", value=0), check(type="max_words", value="5"), check(type="min_words", value=True),
    check(type="regex", value="("), check(type="regex", value=""),
    check(type="order", value=["only one"]), check(type="one_of", value=[]), check(type="json_keys", value="a"),
    check(type="json_valid", value="x"), check(path=""), check(whole_word="yes"), check(surprise=1), "not an object",
])
def test_invalid_checks_are_rejected(bad):
    assert gv.validate_check(bad), bad


@pytest.mark.parametrize("good", [
    {"id": "c1", "type": "json_valid", "label": "wrong_format"},
    check(), check(type="not_contains", whole_word=True, case_sensitive=False, path="reply"),
    check(type="order", value=["a", "b"]), check(type="one_of", value=["a"], path="k"),
    check(type="regex", value=r"^\d+$"), check(type="min_words", value=3),
])
def test_valid_checks_are_accepted(good):
    assert gv.validate_check(good) == []


def test_extract_json_array_handles_fences_and_prose():
    arr = '[{"a": 1}]'
    assert gv.extract_json_array(arr) == [{"a": 1}]
    assert gv.extract_json_array("```json\n" + arr + "\n```") == [{"a": 1}]
    assert gv.extract_json_array("Sure, here you go:\n" + arr + "\nHope it helps") == [{"a": 1}]
    assert gv.extract_json_array('{"a": 1}') is None
    assert gv.extract_json_array("no json here") is None
    assert gv.extract_json_array("") is None


def fake(*replies):
    """A call() that returns the replies in order and records the prompts."""
    prompts = []
    it = iter(replies)

    def call(prompt, model=None):
        prompts.append(prompt)
        return next(it)

    call.prompts = prompts
    return call


def test_generate_keeps_valid_drops_invalid_and_sets_ids():
    v1 = variant(input="Input one.")
    v2 = variant(input="Input two.", difficulty_tags=["bogus"])
    v3 = variant(input="Input three.")
    call = fake(json.dumps([v1, v2, v3]))
    valid, dropped = gv.generate_for_task(SRC, "SKILL TEXT", 3, call=call)
    assert [t["task_id"] for t in valid] == ["t01-v1", "t01-v3"]
    assert all(t["skill_file"] == SRC["skill_file"] and t["source_task_id"] == "t01" and t["generated"] for t in valid)
    assert len(dropped) == 1 and "difficulty_tags" in dropped[0]["reason"] and dropped[0]["raw"]["input"] == "Input two."
    assert "SKILL TEXT" in call.prompts[0] and SRC["input"] in call.prompts[0] and "3 harder variants" in call.prompts[0]


def test_duplicate_variant_inputs_are_dropped():
    v = variant(input="Same input.")
    valid, dropped = gv.generate_for_task(SRC, "S", 3, call=fake(json.dumps([v, v, variant(input="Other.")])))
    assert [t["task_id"] for t in valid] == ["t01-v1", "t01-v3"] and "duplicates" in dropped[0]["reason"]


def test_model_supplied_task_id_is_ignored():
    v = variant(task_id="t99", skill_file=SRC["skill_file"])
    valid, _ = gv.generate_for_task(SRC, "S", 3, call=fake(json.dumps([v])))
    assert valid[0]["task_id"] == "t01-v1"


def test_retry_once_when_reply_is_not_json_then_give_up():
    call = fake("sorry, no", json.dumps([variant()]))
    valid, dropped = gv.generate_for_task(SRC, "S", 3, call=call)
    assert len(valid) == 1 and len(call.prompts) == 2
    assert len(dropped) == 2 and all("fewer variants" in d["reason"] for d in dropped)
    valid, dropped = gv.generate_for_task(SRC, "S", 3, call=fake("no", "still no"))
    assert valid == [] and len(dropped) == 3 and dropped[0]["reason"] == "reply was not a JSON array"


def test_extra_variants_beyond_n_are_ignored():
    valid, dropped = gv.generate_for_task(SRC, "S", 2, call=fake(json.dumps([variant(input=f"i{k}") for k in range(5)])))
    assert len(valid) == 2 and dropped == []


def test_a_valid_variant_runs_through_the_scorer():
    v = gv.generate_for_task(SRC, "S", 3, call=fake(json.dumps([variant()])))[0][0]
    assert score_output(v, json.dumps({"a": "short", "b": "x"}))["passed"] is True
    assert score_output(v, "not json")["passed"] is False


def test_main_writes_separate_files_and_never_touches_tasks_json(tmp_path, monkeypatch):
    before = gv.TASKS_FILE.read_bytes()
    monkeypatch.setattr(gv, "DROPPED_LOG", tmp_path / "dropped.json")
    monkeypatch.setattr(gv.client, "call_llm",
                        lambda p, m=None: json.dumps([variant(input="N1"), variant(input="N2", title="")]))
    out = tmp_path / "tasks_generated.json"
    assert gv.main(["--only", "t01,t02", "--out", str(out), "--variants", "2", "--sleep", "0"]) == 0
    gen = json.loads(out.read_text(encoding="utf-8"))
    assert [t["task_id"] for t in gen] == ["t01-v1", "t02-v1"]
    log = json.loads((tmp_path / "dropped.json").read_text(encoding="utf-8"))
    assert len(log["dropped"]) == 2
    assert gv.TASKS_FILE.read_bytes() == before


def test_main_refuses_to_overwrite_tasks_json():
    assert gv.main(["--out", str(gv.TASKS_FILE)]) == 1


def test_review_sample_is_deterministic_and_readable(tmp_path):
    gen = [dict(variant(input=f"in {k}"), task_id=f"t01-v{k}", source_task_id="t01", skill_file="s", generated=True)
           for k in range(1, 6)]
    a, b = gv.review_sample(gen, 3, seed=7), gv.review_sample(gen, 3, seed=7)
    assert a == b and a.count("===") == 3 and "c3 [ignored_constraint] max_words" in a
    p = tmp_path / "g.json"
    p.write_text(json.dumps(gen), encoding="utf-8")
    assert gv.main(["--out", str(p), "--review", "2"]) == 0
