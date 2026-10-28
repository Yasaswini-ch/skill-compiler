"""Validates benchmark/tasks.json and the skills it uses, and checks every task against golden answers."""
import json
import re
from pathlib import Path

import pytest

from benchmark.scorer import CHECKS, score_output
from benchmark.tests.golden import GOLDEN

ROOT = Path(__file__).resolve().parents[2]
TASKS = json.loads((ROOT / "benchmark" / "tasks.json").read_text(encoding="utf-8"))
LABELS = {"skipped_step", "wrong_format", "lost_track", "merged_steps", "hallucinated_step",
          "ignored_constraint", "other"}
TAGS = {"similar_steps", "strict_format", "step_order", "hard_limits", "arithmetic", "long_instructions"}
IDS = [t["task_id"] for t in TASKS]


def test_ten_tasks_with_unique_ids():
    assert len(TASKS) == 10 and len(set(IDS)) == 10


def test_all_four_difficulty_types_are_covered():
    primary = [t["difficulty_tags"][0] for t in TASKS]
    assert primary.count("similar_steps") == 3
    assert primary.count("strict_format") == 3
    assert primary.count("step_order") == 2
    assert primary.count("hard_limits") == 2


@pytest.mark.parametrize("task", TASKS, ids=IDS)
def test_task_shape(task):
    assert {"task_id", "title", "skill_file", "input", "difficulty_tags", "checks"} <= set(task)
    assert set(task["difficulty_tags"]) <= TAGS
    assert 4 <= len(task["checks"]) <= 7
    ids = [c["id"] for c in task["checks"]]
    assert ids == [f"c{i}" for i in range(1, len(ids) + 1)]
    for c in task["checks"]:
        assert c["type"] in CHECKS and c["label"] in LABELS
        if c["type"] != "json_valid":
            assert "value" in c
        if c["type"] == "regex":
            re.compile(c["value"])
    assert (ROOT / task["skill_file"]).is_file()


SKILL_FILES = sorted((ROOT / "skills").glob("*/SKILL.md"))


def test_five_or_six_skills_used_by_tasks():
    assert 5 <= len(SKILL_FILES) <= 6
    assert {t["skill_file"] for t in TASKS} == {p.relative_to(ROOT).as_posix() for p in SKILL_FILES}


@pytest.mark.parametrize("path", SKILL_FILES, ids=[p.parent.name for p in SKILL_FILES])
def test_skill_format(path):
    text = path.read_text(encoding="utf-8")
    front = re.match(r"---\n(.*?)\n---\n", text, re.DOTALL)
    assert front, "missing YAML frontmatter"
    fields = dict(line.split(": ", 1) for line in front.group(1).splitlines())
    assert fields["name"] == path.parent.name
    assert re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", fields["name"]) and len(fields["name"]) <= 64
    assert 0 < len(fields["description"]) <= 1024
    numbered = re.findall(r"^(\d+)\. ", text, re.MULTILINE)
    assert 6 <= len(numbered) <= 12
    assert numbered == [str(i) for i in range(1, len(numbered) + 1)]


def test_every_task_has_golden_answers():
    assert set(GOLDEN) == set(IDS)
    for tid, g in GOLDEN.items():
        assert len(g["good"]) >= 1 and len(g["bad"]) >= 3, tid


@pytest.mark.parametrize("task", TASKS, ids=IDS)
def test_good_answers_pass_every_check(task):
    for out in GOLDEN[task["task_id"]]["good"]:
        r = score_output(task, out)
        assert r["passed"], (r["failed_checks"], r["details"])


@pytest.mark.parametrize("task", TASKS, ids=IDS)
def test_bad_answers_fail_exactly_the_expected_checks(task):
    for out, expected in GOLDEN[task["task_id"]]["bad"]:
        r = score_output(task, out)
        assert set(r["failed_checks"]) == expected, (out[:80], r["failed_checks"], r["details"])


def test_every_check_is_exercised_by_a_bad_answer():
    """Each check must be able to fail, otherwise it proves nothing."""
    for task in TASKS:
        hit = set()
        for _, expected in GOLDEN[task["task_id"]]["bad"]:
            hit |= expected
        assert hit >= {c["id"] for c in task["checks"]}, (task["task_id"], hit)


def test_t06_eggs_row_accepts_both_original_forms_and_rejects_wrong_values():
    """t06 fix (FROZEN.md): the original quantity may keep a trailing "eggs"; wrong numbers still fail."""
    task = next(t for t in TASKS if t["task_id"] == "t06")
    base = GOLDEN["t06"]["good"][0]
    row = "| eggs | 2 | 7.0 |"
    assert row in base
    for ok in ("| eggs | 2 | 7.0 |", "| eggs | 2 eggs | 7.0 eggs |", "| eggs | 2 | 7.0 eggs |", "| Eggs | 2 eggs | 7.0 |"):
        assert score_output(task, base.replace(row, ok))["passed"], ok
    for wrong in ("| eggs | 2 eggs | 7 eggs |", "| eggs | 2 eggs | 8.0 eggs |", "| eggs | 3 eggs | 7.0 eggs |",
                  "| eggs | 2 eggs | 7.0 eggs extra |"):
        assert score_output(task, base.replace(row, wrong))["failed_checks"] == ["c4"], wrong
