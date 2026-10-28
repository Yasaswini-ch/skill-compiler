"""Tests for benchmark/build_experiment_results.py (offline)."""
import json
from pathlib import Path

import pytest

from benchmark import build_experiment_results as be

OFFICIAL = Path(be.ROOT) / "benchmark" / "output" / "results.json"


def results(passed_plain, passed_harness, mock=False, sha="abc", model="m", provider="gemini", cache=False):
    def cell(ok, calls, ms):
        return {"passed": ok, "llm_calls": calls, "latency_ms": ms}
    tasks = [{"task_id": f"t{i + 1:02d}", "plain": cell(i < passed_plain, 1, 2000), "harness": cell(i < passed_harness, 15, 40000)}
             for i in range(4)]
    return {"model": model, "provider": provider, "generated_at": "2026-10-28T12:30:22+05:30", "tasks_sha256": sha,
            "harness_is_mock": mock, "gemma_thinking": "MINIMAL", "verifier": "on", "cache_used": cache, "tasks": tasks}


def write(tmp_path, name, data):
    p = tmp_path / name
    p.write_text(json.dumps(data), encoding="utf-8")
    return p


def test_rows_hold_totals_of_one_run(tmp_path):
    doc = be.build([("M", write(tmp_path, "a.json", results(3, 4)))], {"M": "note"})
    plain, harness = doc["configs"]
    assert plain == {"name": "M, plain", "model": "m", "provider": "gemini", "mode": "plain", "passed": 3, "total": 4,
                     "llm_calls": 4, "latency_s": 8.0, "failed_tasks": ["t04"], "notes": "note"}
    assert harness["mode"] == "harness" and harness["passed"] == 4 and harness["llm_calls"] == 60
    assert harness["latency_s"] == 160.0 and harness["failed_tasks"] == []
    assert doc["n_tasks"] == 4 and doc["settings"] == {"thinking": "MINIMAL", "verifier": "on", "cache": False, "runs_per_config": 1}
    assert doc["mock"] is False and doc["tasks_file"] == "benchmark/tasks.json"
    assert not any(c["mode"] == "adaptive" for c in doc["configs"])  # no adaptive row without a saved adaptive run


def test_mock_and_cache_are_carried_over(tmp_path):
    doc = be.build([("M", write(tmp_path, "a.json", results(1, 1, mock=True, cache=True)))], {})
    assert doc["mock"] is True and doc["settings"]["cache"] is True
    assert "notes" not in doc["configs"][0]


def test_two_runs_on_the_same_tasks_share_one_table(tmp_path):
    doc = be.build([("A", write(tmp_path, "a.json", results(3, 4))),
                    ("B", write(tmp_path, "b.json", results(1, 2, model="small", provider="openai-compatible")))], {})
    assert [c["name"] for c in doc["configs"]] == ["A, plain", "A, harness", "B, plain", "B, harness"]
    assert doc["configs"][2]["provider"] == "openai-compatible" and doc["configs"][2]["model"] == "small"


def test_different_task_sets_are_refused(tmp_path):
    with pytest.raises(ValueError, match="different task set"):
        be.build([("A", write(tmp_path, "a.json", results(1, 1))), ("B", write(tmp_path, "b.json", results(1, 1, sha="zzz")))], {})


def test_old_results_without_a_provider_count_as_gemini(tmp_path):
    r = results(1, 1)
    del r["provider"]
    assert be.build([("A", write(tmp_path, "a.json", r))], {})["configs"][0]["provider"] == "gemini"


def test_main_validates_its_arguments(tmp_path, capsys):
    assert be.main(["--run", "no-equals-sign"]) == 1
    assert "NAME=VALUE" in capsys.readouterr().err
    assert be.main(["--run", f"A={tmp_path / 'missing.json'}"]) == 1


def test_main_writes_a_file_that_matches_the_contract_schema(tmp_path):
    jsonschema = pytest.importorskip("jsonschema")
    out = tmp_path / "e.json"
    assert be.main(["--run", f"A={write(tmp_path, 'a.json', results(3, 4))}", "--out", str(out)]) == 0
    schema = json.loads((Path(be.ROOT) / "contract" / "phase2" / "experiment_results.schema.json").read_text(encoding="utf-8"))
    jsonschema.validate(json.loads(out.read_text(encoding="utf-8")), schema)


def test_the_official_run_gives_the_headline_numbers():
    """Run 1 is the official result: plain 7/10, harness 9/10 (RESULTS_NOTE.md)."""
    doc = be.build([("Official", OFFICIAL)], {})
    plain, harness = doc["configs"]
    assert (plain["passed"], plain["total"], plain["failed_tasks"]) == (7, 10, ["t04", "t05", "t08"])
    assert (harness["passed"], harness["total"], harness["failed_tasks"]) == (9, 10, ["t03"])
    assert doc["tasks_sha256"].startswith("53351f62")
