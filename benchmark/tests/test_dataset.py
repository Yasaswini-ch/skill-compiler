"""Tests for benchmark/dataset/export_dataset.py (no model calls)."""
import json

import pytest

from benchmark.dataset import export_dataset as ex

TASKS = [{"task_id": "t01", "title": "T1", "skill_file": "skills/a/SKILL.md", "input": "i",
          "difficulty_tags": ["strict_format"], "checks": []}]


def results(passed=False, scorer_label=None):
    cell = {"passed": passed, "failure_label": "other", "failed_checks": ["c1"]}
    if scorer_label:
        cell["scorer_label"] = scorer_label
    return {"model": "m", "verifier": "on", "gemma_thinking": "MINIMAL", "tasks_sha256": "abc",
            "tasks": [{"task_id": "t01", "plain": cell, "harness": {"passed": True}}]}


def failure(label="other"):
    return {"failure_id": "f001", "task_id": "t01", "mode": "plain", "label": label,
            "what_went_wrong": "c1: x", "failed_checks": ["c1"], "output_excerpt": "out", "label_note": "why"}


def test_failure_record_has_settings_and_scorer_label():
    rec = ex.failure_records(results(scorer_label="lost_track"), [failure()], TASKS)[0]
    assert rec["label"] == "other" and rec["scorer_label"] == "lost_track" and rec["label_note"] == "why"
    assert rec["task_title"] == "T1" and rec["run"] == 1 and rec["model"] == "m" and rec["verifier"] == "on"
    assert rec["tasks_sha256"] == "abc" and rec["difficulty_tags"] == ["strict_format"]


def test_no_scorer_label_when_the_label_was_not_changed():
    rec = ex.failure_records(results(scorer_label="other"), [failure()], TASKS)[0]
    assert "scorer_label" not in rec


def test_rejects_unknown_label_and_a_failure_that_passed():
    with pytest.raises(ValueError, match="unknown label"):
        ex.failure_records(results(), [failure("nope")], TASKS)
    with pytest.raises(ValueError, match="passed"):
        ex.failure_records(results(passed=True), [failure()], TASKS)


def test_task_records_embed_the_skill_text():
    recs = ex.task_records(TASKS, lambda path: f"TEXT of {path}")
    assert recs[0]["skill_text"] == "TEXT of skills/a/SKILL.md" and recs[0]["task_id"] == "t01"
    assert "skill_text" not in TASKS[0]


def test_write_jsonl_one_object_per_line(tmp_path):
    p = tmp_path / "x.jsonl"
    ex.write_jsonl(p, [{"a": 1}, {"b": "é"}])
    lines = p.read_bytes().decode("utf-8").split("\n")
    assert lines[-1] == "" and [json.loads(x) for x in lines[:-1]] == [{"a": 1}, {"b": "é"}]
    assert b"\r" not in p.read_bytes()


def test_exported_files_match_the_official_run():
    """The committed export must agree with output/results.json and failures.json."""
    failures = json.loads((ex.BENCH / "output" / "failures.json").read_text(encoding="utf-8"))
    lines = (ex.OUT_DIR / "failures.jsonl").read_text(encoding="utf-8").splitlines()
    assert [json.loads(x)["failure_id"] for x in lines] == [f["failure_id"] for f in failures]
    tasks = [json.loads(x) for x in (ex.OUT_DIR / "tasks.jsonl").read_text(encoding="utf-8").splitlines()]
    assert [t["task_id"] for t in tasks] == [f"t{i:02d}" for i in range(1, 11)]
    assert all(t["skill_text"].startswith("---") for t in tasks)
