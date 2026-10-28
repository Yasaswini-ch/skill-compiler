"""Checks the 7 hand-checked generated tasks (benchmark/tasks_generated_reviewed.json) against hand-worked answers."""
import json
from pathlib import Path

import pytest

from benchmark import gen_variants as gv
from benchmark.scorer import score_output
from benchmark.tests.golden_generated import GOLDEN_GENERATED

BENCH = Path(__file__).resolve().parents[1]
REVIEWED = json.loads((BENCH / "tasks_generated_reviewed.json").read_text(encoding="utf-8"))
ALL_GENERATED = json.loads((BENCH / "tasks_generated.json").read_text(encoding="utf-8"))
KEPT = ["t01-v2", "t01-v3", "t05-v1", "t06-v2", "t07-v2", "t07-v3", "t08-v3"]
DROPPED_AFTER_REVIEW = ["t03-v1", "t03-v2", "t04-v2", "t04-v3", "t09-v1"]

def params():
    return [pytest.param(t, id=t["task_id"]) for t in REVIEWED]


def test_reviewed_file_has_exactly_the_kept_tasks():
    assert [t["task_id"] for t in REVIEWED] == KEPT
    assert not set(DROPPED_AFTER_REVIEW) & {t["task_id"] for t in REVIEWED}


def test_reviewed_tasks_are_the_same_as_in_tasks_generated():
    by_id = {t["task_id"]: t for t in ALL_GENERATED}
    assert all(by_id[t["task_id"]] == t for t in REVIEWED)


@pytest.mark.parametrize("task", REVIEWED, ids=[t["task_id"] for t in REVIEWED])
def test_reviewed_task_passes_the_schema(task):
    body = {k: task[k] for k in ("title", "input", "difficulty_tags", "checks")}
    assert gv.validate_task(body) == []
    assert task["generated"] is True and task["source_task_id"] == task["task_id"].split("-v")[0]


def test_every_kept_task_has_golden_answers():
    assert set(GOLDEN_GENERATED) == set(KEPT)
    for tid, g in GOLDEN_GENERATED.items():
        assert g["good"] and len(g["bad"]) >= 5, tid


@pytest.mark.parametrize("task", params())
def test_good_answers_pass_every_check(task):
    for out in GOLDEN_GENERATED[task["task_id"]]["good"]:
        r = score_output(task, out)
        assert r["passed"], (r["failed_checks"], r["details"])


@pytest.mark.parametrize("task", params())
def test_bad_answers_fail_exactly_the_expected_checks(task):
    for out, expected in GOLDEN_GENERATED[task["task_id"]]["bad"]:
        r = score_output(task, out)
        assert set(r["failed_checks"]) == expected, (out[:80], r["failed_checks"], r["details"])


def test_every_check_is_exercised_by_a_bad_answer():
    for task in REVIEWED:
        hit = set()
        for _, expected in GOLDEN_GENERATED[task["task_id"]]["bad"]:
            hit |= expected
        assert hit >= {c["id"] for c in task["checks"]}, (task["task_id"], hit)


def test_t08_v3_scale_factor_accepts_10_and_10_point_0_only():
    """The one edit made to a generated task after review (GENERATED_REVIEW.md)."""
    task = next(t for t in REVIEWED if t["task_id"] == "t08-v3")
    base = GOLDEN_GENERATED["t08-v3"]["good"][0]
    assert next(c for c in task["checks"] if c["id"] == "c5")["value"] == r"(?m)^Scale factor:\s*10(\.0)?\s*\Z"
    for ok in ("Scale factor: 10", "Scale factor: 10.0", "Scale factor:10"):
        assert score_output(task, base.replace("Scale factor: 10", ok))["passed"], ok
    for bad in ("Scale factor: 10.5", "Scale factor: 100", "Scale factor: 1", "Scale factor: 10.00"):
        assert score_output(task, base.replace("Scale factor: 10", bad))["failed_checks"] == ["c5"], bad


def test_t07_v2_four_line_check_strips_surrounding_whitespace_only():
    task = next(t for t in REVIEWED if t["task_id"] == "t07-v2")
    good = GOLDEN_GENERATED["t07-v2"]["good"][0]
    for out in ("\n\n" + good + "\n\n", "  " + good + "   \n", "\t" + good + "\n"):
        assert score_output(task, out)["passed"], repr(out[:20])
    for out in (good.replace("\nHotel", "\n\nHotel"), good + "\nextra", "intro\n" + good):
        assert "c5" in score_output(task, out)["failed_checks"], repr(out[:30])


def test_t05_v1_correct_answer_passes_and_each_wrong_answer_fails_exactly_one_check():
    """t05-v1 fix (GENERATED_REVIEW.md): c4-c7 had literal quotes and could never match; no cascade now."""
    task = next(t for t in REVIEWED if t["task_id"] == "t05-v1")
    assert [c["value"] for c in task["checks"][3:]] == [r"441\.60", r"44\.16", "31.80", "429.24"]
    good = json.loads(GOLDEN_GENERATED["t05-v1"]["good"][0])
    assert score_output(task, json.dumps(good))["passed"]
    for field, wrong, check in [("invoice", "8821", "c3"), ("subtotal", "441.00", "c4"), ("discount", "0.00", "c5"),
                                ("tax", "31.79", "c6"), ("total", "429.25", "c7")]:
        r = score_output(task, json.dumps({**good, field: wrong}))
        assert r["failed_checks"] == [check], (field, r["failed_checks"])
    r = score_output(task, json.dumps({**good, "currency": "USD"}))
    assert r["failed_checks"] == ["c2"]


def test_recorded_hash_matches_the_reviewed_file():
    """GENERATED_REVIEW.md records the SHA-256 of the frozen reviewed file; it must match what is on disk."""
    import hashlib
    import re

    text = (BENCH / "GENERATED_REVIEW.md").read_text(encoding="utf-8")
    section = text.split("## Reviewed file", 1)[1].split("\n## ", 1)[0]
    recorded = re.search(r"^\| SHA-256 \| `([0-9a-f]{64})`", section, re.MULTILINE).group(1)
    actual = hashlib.sha256((BENCH / "tasks_generated_reviewed.json").read_bytes()).hexdigest()
    assert recorded == actual
    assert "Frozen before any run" in section
