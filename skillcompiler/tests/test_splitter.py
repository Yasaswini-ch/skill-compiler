import json

import pytest

from skillcompiler import llm, splitter

SKILL = """---
name: demo
description: demo skill
---
1. Extract the name.
2. Classify as billing or technical.
   Use one word only.
3. Output JSON with key name.
"""

GOOD = {"steps": [
    {"id": 1, "title": "Name", "instruction": "Extract the name.",
     "output_format": "text", "expected_output": "a name", "depends_on": []},
    {"id": 2, "title": "Class", "instruction": "Classify.",
     "output_format": "one_of:billing|technical", "expected_output": "one word",
     "depends_on": [1]},
]}


def fake_llm(monkeypatch, replies):
    it = iter(replies)
    monkeypatch.setattr(llm, "call_llm", lambda prompt, model=None, retries=3: next(it))


def test_model_plan(monkeypatch):
    fake_llm(monkeypatch, [json.dumps(GOOD)])
    plan = splitter.compile_skill(SKILL, source_file="x/SKILL.md")
    assert plan["skill_name"] == "demo" and plan["source_file"] == "x/SKILL.md"
    assert [s["id"] for s in plan["steps"]] == [1, 2]
    assert plan["steps"][1]["output_format"] == "one_of:billing|technical"


def test_fenced_json(monkeypatch):
    fake_llm(monkeypatch, ["```json\n" + json.dumps(GOOD) + "\n```"])
    assert len(splitter.compile_skill(SKILL)["steps"]) == 2


def test_retry_once_on_bad_json(monkeypatch):
    fake_llm(monkeypatch, ["not json", json.dumps(GOOD)])
    assert len(splitter.compile_skill(SKILL)["steps"]) == 2


def test_fallback_to_rules(monkeypatch):
    fake_llm(monkeypatch, ["nope", "still nope"])
    plan = splitter.compile_skill(SKILL)
    assert [s["id"] for s in plan["steps"]] == [1, 2, 3]
    assert "one word only" in plan["steps"][1]["instruction"]
    assert plan["steps"][2]["depends_on"] == [2]


def test_fallback_when_llm_raises(monkeypatch):
    def boom(prompt, model=None, retries=3):
        raise RuntimeError("down")
    monkeypatch.setattr(llm, "call_llm", boom)
    assert len(splitter.compile_skill(SKILL)["steps"]) == 3


def test_rules_headings_and_paragraphs():
    heads = splitter.rule_based_steps("## First\nDo a.\n## Second\nDo b.")
    assert [s["title"] for s in heads] == ["First", "Second"]
    paras = splitter.rule_based_steps("Do a.\n\nDo b.")
    assert len(paras) == 2


@pytest.mark.parametrize("steps", [
    [],
    [{"id": 1, "instruction": ""}],
    [{"id": 1, "instruction": "a"}, {"id": 1, "instruction": "b"}],
    [{"id": 1, "instruction": "a", "depends_on": [2]}, {"id": 2, "instruction": "b"}],
])
def test_validation_rejects(steps):
    with pytest.raises(ValueError):
        splitter.validate_steps(steps)


def test_bad_format_becomes_text():
    out = splitter.validate_steps([{"id": 1, "instruction": "a", "output_format": "weird"}])
    assert out[0]["output_format"] == "text"


LIMIT_SKILL = '''---
name: limits
---
1. Write a reply of at most 60 words. It must begin with "Hi <name>,".
2. Rate urgency from 1 to 5.
3. Output JSON.
'''


def plan_with(*instructions):
    return json.dumps({"steps": [
        {"id": i, "title": f"S{i}", "instruction": t, "output_format": "text",
         "expected_output": "", "depends_on": [i - 1] if i > 1 else []}
        for i, t in enumerate(instructions, start=1)]})


def test_requirement_tokens_ignore_list_numbering():
    body = splitter._parse_frontmatter(LIMIT_SKILL)[1]
    assert splitter.requirement_tokens(body) == ["Hi <name>,", "60", "1", "5"]


def test_nothing_missing_when_plan_keeps_everything(monkeypatch):
    calls = []
    good = plan_with('Reply of at most 60 words, begin with "Hi <name>,".', "Rate urgency 1 to 5.", "Output JSON.")

    def f(prompt, model=None, retries=3):
        calls.append(prompt)
        return good

    monkeypatch.setattr(llm, "call_llm", f)
    plan = splitter.compile_skill(LIMIT_SKILL)
    assert "warnings" not in plan and len(calls) == 1


def test_dropped_limit_triggers_one_resplit(monkeypatch):
    bad = plan_with("Write a reply.", "Rate urgency.", "Output JSON.")
    good = plan_with('Reply of at most 60 words, begin with "Hi <name>,".', "Rate urgency 1 to 5.", "Output JSON.")
    prompts = []
    replies = iter([bad, good])

    def f(prompt, model=None, retries=3):
        prompts.append(prompt)
        return next(replies)

    monkeypatch.setattr(llm, "call_llm", f)
    plan = splitter.compile_skill(LIMIT_SKILL)
    assert len(prompts) == 2 and "left out these items" in prompts[1] and '"Hi <name>,"' in prompts[1]
    assert "warnings" not in plan and "60 words" in plan["steps"][0]["instruction"]


def test_still_missing_is_a_warning_not_silent(monkeypatch):
    bad = plan_with("Write a reply.", "Rate urgency.", "Output JSON.")
    fake_llm(monkeypatch, [bad, bad])
    plan = splitter.compile_skill(LIMIT_SKILL)
    assert len(plan["steps"]) == 3
    assert "60" in plan["warnings"][0] and "Hi <name>," in plan["warnings"][0]


def test_resplit_failure_keeps_first_plan(monkeypatch):
    bad = plan_with("Write a reply.", "Rate urgency.", "Output JSON.")
    fake_llm(monkeypatch, [bad, "not json", "still not json"])
    plan = splitter.compile_skill(LIMIT_SKILL)
    assert plan["steps"][0]["instruction"] == "Write a reply." and plan["warnings"]


def test_rule_based_fallback_has_no_warnings(monkeypatch):
    fake_llm(monkeypatch, ["nope", "nope"])
    assert "warnings" not in splitter.compile_skill(LIMIT_SKILL)
