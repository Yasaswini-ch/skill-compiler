"""Tests for benchmark/autorewrite.py with a fake model. No API calls."""
import json
import shutil

import pytest

from benchmark import autorewrite as ar
from benchmark.tests.golden import GOLDEN

SKILL = ar.ROOT / "skills" / "trip-day-planner" / "SKILL.md"


def test_clean_rewrite_strips_a_wrapping_fence():
    assert ar.clean_rewrite("```markdown\n---\nname: x\n---\n1. a\n```") == "---\nname: x\n---\n1. a\n"
    assert ar.clean_rewrite("  plain  ") == "plain\n"


def test_lost_constraints_finds_dropped_numbers_and_phrases():
    original = 'Write at most 60 words. It must begin with "Hi <name>,". Use 2 decimals.'
    assert ar.lost_constraints(original, 'At most 60 words. Begin with "Hi <name>,". 2 decimals.') == []
    lost = ar.lost_constraints(original, "Write briefly. Begin politely. 2 decimals.")
    assert "number 60" in lost and 'phrase "Hi <name>,"' in lost and "number 2" not in lost


def test_lost_constraints_does_not_match_a_number_inside_a_longer_one():
    assert "number 5" in ar.lost_constraints("Rate from 1 to 5.", "Rate from 1 to 15.")


def test_the_real_skills_lose_nothing_when_rewritten_to_themselves():
    for p in sorted((ar.ROOT / "skills").glob("*/SKILL.md")):
        text = p.read_text(encoding="utf-8")
        assert ar.lost_constraints(text, text) == [], p.parent.name


class FakeModel:
    """Rewrites the skill into itself plus a note; answers plain prompts with the golden answer for t07."""

    def __init__(self, rewritten_skill=None, plain_original="good", plain_rewritten="bad"):
        self.prompts = []
        self.rewritten_skill = rewritten_skill
        self.plain = {"original": plain_original, "rewritten": plain_rewritten}

    def __call__(self, prompt, model=None):
        self.prompts.append(prompt)
        if prompt.startswith("Rewrite the agent skill"):
            return self.rewritten_skill or SKILL.read_text(encoding="utf-8").replace("# Trip day planner", "# Trip day planner (rewritten)")
        which = "rewritten" if "(rewritten)" in prompt else "original"
        return GOLDEN["t07"]["good"][0] if self.plain[which] == "good" else "no idea"


@pytest.fixture
def skill_copy(tmp_path, monkeypatch):
    """Run against a copy of the skill inside a temporary 'repo' so no real file is written."""
    root = tmp_path / "repo"
    (root / "skills" / "trip-day-planner").mkdir(parents=True)
    shutil.copy(SKILL, root / "skills" / "trip-day-planner" / "SKILL.md")
    monkeypatch.setattr(ar, "ROOT", root)
    return root / "skills" / "trip-day-planner" / "SKILL.md"


def test_end_to_end_with_a_fake_model(skill_copy, tmp_path, capsys):
    model = FakeModel(plain_original="good", plain_rewritten="bad")
    out = tmp_path / "report.json"
    assert ar.main([str(skill_copy), "--sleep", "0", "--out", str(out)], call=model) == 0
    text = capsys.readouterr().out
    assert "t07" in text and "TOTAL" in text and "1/1" in text and "0/1" in text
    rewritten = skill_copy.with_name("SKILL.rewritten.md")
    assert rewritten.read_text(encoding="utf-8").startswith("---") and "(rewritten)" in rewritten.read_text(encoding="utf-8")
    report = json.loads(out.read_text(encoding="utf-8"))
    assert report["skill"] == "skills/trip-day-planner/SKILL.md" and report["rewrite_warnings"] == []
    assert [(r["version"], r["passed"]) for r in report["runs"]] == [("original", True), ("rewritten", False)]
    assert len(model.prompts) == 3  # 1 rewrite + 1 task x 2 versions
    assert skill_copy.read_text(encoding="utf-8") == SKILL.read_text(encoding="utf-8")  # the original is untouched


def test_rewrite_that_drops_a_constraint_is_reported(skill_copy, tmp_path, capsys):
    model = FakeModel(rewritten_skill="---\nname: trip-day-planner\n---\n1. Do the trip plan.\n")
    out = tmp_path / "r.json"
    ar.main([str(skill_copy), "--sleep", "0", "--out", str(out)], call=model)
    err = capsys.readouterr().err
    assert "WARNING" in err and "number 45" in err and "phrase" not in err.split("number 45")[0]
    assert json.loads(out.read_text(encoding="utf-8"))["rewrite_warnings"]


def test_repeats_multiply_the_runs(skill_copy, tmp_path):
    model = FakeModel()
    ar.main([str(skill_copy), "--sleep", "0", "--repeats", "3", "--out", str(tmp_path / "r.json")], call=model)
    assert len(model.prompts) == 1 + 2 * 3


def test_skill_without_tasks_is_an_error(tmp_path, monkeypatch, capsys):
    root = tmp_path / "repo"
    (root / "skills" / "other").mkdir(parents=True)
    (root / "skills" / "other" / "SKILL.md").write_text("---\nname: other\n---\n1. x\n", encoding="utf-8")
    monkeypatch.setattr(ar, "ROOT", root)
    assert ar.main([str(root / "skills" / "other" / "SKILL.md")], call=FakeModel()) == 1
    assert "no tasks use" in capsys.readouterr().err
