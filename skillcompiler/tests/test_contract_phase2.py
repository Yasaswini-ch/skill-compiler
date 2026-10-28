import json
from pathlib import Path

import pytest

jsonschema = pytest.importorskip("jsonschema")

DIR = Path(__file__).resolve().parents[2] / "contract" / "phase2"
EVENT_TYPES = {"run_start", "plan", "step_start", "attempt_start", "attempt_end", "step_end", "run_end", "error"}


def load(name):
    return json.loads((DIR / name).read_text(encoding="utf-8"))


def schema(name):
    return load(name + ".schema.json")


@pytest.mark.parametrize("data_file,schema_name", [
    ("experiment_results.json", "experiment_results"),
    ("attack_presets.json", "attack_presets"),
    ("mode_detail.json", "trace_mode_detail"),
])
def test_mock_file_matches_its_schema(data_file, schema_name):
    jsonschema.validate(load(data_file), schema(schema_name))


def test_every_arena_line_matches_the_schema():
    lines = (DIR / "arena_log.jsonl").read_text(encoding="utf-8").splitlines()
    assert lines
    for line in lines:
        jsonschema.validate(json.loads(line), schema("arena_log_line"))


def test_free_play_rows_are_never_scored():
    for line in (DIR / "arena_log.jsonl").read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        if row["kind"] == "free":
            assert row["broke_plain"] is None and row["plain"]["passed"] is None and row["preset_id"] is None


def test_mock_files_are_flagged_as_mock():
    assert load("experiment_results.json")["mock"] is True
    assert all(p.get("mock") for p in load("attack_presets.json"))


def test_event_sample_is_a_valid_stream():
    events = [json.loads(l) for l in (DIR / "events_sample.ndjson").read_text(encoding="utf-8").splitlines()]
    assert {e["type"] for e in events} <= EVENT_TYPES
    assert events[0]["type"] == "run_start" and events[-1]["type"] == "run_end"
    assert events[-1]["trace"]["mock"] is True
    assert any(e["type"] == "attempt_end" and e["ok"] is False for e in events)  # shows a retry


def test_experiment_results_internally_consistent():
    data = load("experiment_results.json")
    for c in data["configs"]:
        assert 0 <= c["passed"] <= c["total"] == data["n_tasks"]
        assert len(c["failed_tasks"]) == c["total"] - c["passed"]
