"""Tests for benchmark/build_presets.py with a fake runner. No API calls."""
import json
from pathlib import Path

import pytest

from benchmark import build_presets as bp
from benchmark.presets_src import PRESET_SPECS
from benchmark.tests.golden_presets import GOLDEN_PRESETS

SPEC = PRESET_SPECS[0]
SETTINGS = {"model": "m1", "provider": "gemini", "gemma_thinking": "MINIMAL", "verifier": "on", "harness_mode": "adaptive"}


def trace(output, mode="plain", steps=(), calls=1):
    return {"mode": mode, "final_output": output, "steps": list(steps),
            "totals": {"llm_calls": calls, "latency_ms": 1000, "retries": 0}}


def step(status="pass", note="ok"):
    return {"step_id": 1, "title": "t", "status": status, "attempts": [{"output": "x", "checker_note": note}]}


GOOD = GOLDEN_PRESETS["p01"]["good"][0]
BAD = GOLDEN_PRESETS["p01"]["bad"][3][0]  # wrong subtotal


def doc(runs=()):
    return {"settings": {**SETTINGS, "started_at": "2026-10-28T20:00:00+05:30"}, "runs": list(runs)}


def rec(pid, mode, index, passed, api_error=False):
    return {"preset_id": pid, "mode": mode, "index": index, "passed": None if api_error else passed,
            "failed_checks": [] if passed else ["c3"], "api_error": api_error, "error": None, "output": "",
            "llm_calls": 1, "latency_ms": 1000}


def test_tag_rules():
    assert bp.tag_for(0, 0) == "untested"
    assert bp.tag_for(0, 5) is None
    assert bp.tag_for(5, 5) == "reliable" and bp.tag_for(4, 5) == "reliable"
    assert bp.tag_for(3, 5) == "sometimes" and bp.tag_for(1, 5) == "sometimes"


def test_plain_record_scores_the_output():
    ok = bp._record(SPEC, "plain", 1, trace(GOOD), None)
    bad = bp._record(SPEC, "plain", 2, trace(BAD), None)
    assert ok["passed"] is True and ok["api_error"] is False and ok["failed_checks"] == []
    assert bad["passed"] is False and bad["failed_checks"] == ["c3"] and bad["api_error"] is False


def test_a_failed_model_call_is_an_api_error_not_a_failure():
    r = bp._record(SPEC, "plain", 1, None, "RuntimeError: LLM call failed after 3 tries")
    assert r["api_error"] is True and r["passed"] is None and "LLM call failed" in r["error"]


def test_harness_run_with_an_api_error_counts_only_if_it_failed():
    api = step("fail", "LLM call failed: 500")
    failed = bp._record(SPEC, "harness", 1, trace(BAD, "harness", [api]), None)
    passed = bp._record(SPEC, "harness", 2, trace(GOOD, "harness", [step("repaired", "LLM call failed: 500")]), None)
    clean_fail = bp._record(SPEC, "harness", 3, trace(BAD, "harness", [step("pass")]), None)
    assert failed["api_error"] is True
    assert passed["api_error"] is False and passed["passed"] is True and passed["api_errors_in_run"] == 1
    assert clean_fail["api_error"] is False and clean_fail["passed"] is False
    assert clean_fail["steps"] == {"pass": 1, "repaired": 0, "fail": 0}


def test_run_once_never_raises(monkeypatch):
    monkeypatch.setattr(bp, "run_plain", lambda s, i: (_ for _ in ()).throw(RuntimeError("down")))
    r = bp.run_once(SPEC, "plain", 1, "adaptive")
    assert r["api_error"] is True and "RuntimeError: down" in r["error"]


def test_run_once_passes_the_harness_mode(monkeypatch):
    seen = {}
    monkeypatch.setattr(bp.harness_adapter, "run_skill", lambda s, i, mode=None: seen.update(mode=mode) or trace(GOOD, "harness"))
    bp.run_once(SPEC, "harness", 1, "adaptive")
    assert seen["mode"] == "adaptive"


def test_test_presets_fills_the_wanted_runs_and_repeats_api_errors(monkeypatch):
    monkeypatch.setattr(bp.time, "sleep", lambda s: None)
    script = iter([False, True, False, False, False])  # plain: ok, api error, ok ; harness: ok, ok

    def fake_run(spec, mode, index, harness_mode):
        err = next(script)
        return rec(spec["id"], mode, index, True, api_error=err)

    d = doc()
    bp.test_presets([SPEC], d, plain_runs=2, harness_runs=2, harness_mode="adaptive", sleep=0, save=lambda x: None, run=fake_run)
    assert len(bp.valid_runs(d, "p01", "plain")) == 2 and len(bp.valid_runs(d, "p01", "harness")) == 2
    assert sum(r["api_error"] for r in d["runs"]) == 1 and len(d["runs"]) == 5
    assert [r["index"] for r in bp.valid_runs(d, "p01", "plain")] == [1, 2]


def test_test_presets_gives_up_after_the_extra_tries(monkeypatch):
    monkeypatch.setattr(bp.time, "sleep", lambda s: None)
    d = doc()
    bp.test_presets([SPEC], d, 1, 0, "adaptive", 0, lambda x: None, run=lambda s, m, i, h: rec(s["id"], m, i, True, api_error=True))
    assert len(d["runs"]) == 1 + bp.EXTRA_TRIES and not bp.valid_runs(d, "p01", "plain")


def test_a_second_call_repeats_nothing(monkeypatch):
    monkeypatch.setattr(bp.time, "sleep", lambda s: None)
    calls = []
    run = lambda s, m, i, h: calls.append((m, i)) or rec(s["id"], m, i, True)
    d = doc()
    bp.test_presets([SPEC], d, 2, 1, "adaptive", 0, lambda x: None, run=run)
    n = len(calls)
    bp.test_presets([SPEC], d, 2, 1, "adaptive", 0, lambda x: None, run=run)
    assert len(calls) == n


def test_build_counts_tags_and_drops():
    runs = ([rec("p01", "plain", i, i > 4) for i in range(1, 6)]            # plain failed 4 of 5 -> reliable
            + [rec("p01", "harness", i, True) for i in range(1, 4)]
            + [rec("p01", "plain", 6, True, api_error=True)]                # excluded
            + [rec("p02", "plain", i, i > 2) for i in range(1, 6)]          # failed 2 of 5 -> sometimes
            + [rec("p02", "harness", 1, False), rec("p02", "harness", 2, True)]
            + [rec("p03", "plain", i, True) for i in range(1, 6)])          # never failed -> dropped
    presets, dropped = bp.build_presets(PRESET_SPECS, doc(runs))
    by = {p["id"]: p for p in presets}
    assert set(by) == {"p01", "p02", "p04", "p05", "p06", "p07", "p08"}  # p03 never broke plain: dropped
    assert [d["id"] for d in dropped] == ["p03"] and "passed all 5 runs" in dropped[0]["reason"]
    assert by["p01"]["tag"] == "reliable" and by["p01"]["tested"] == {
        "model": "m1", "date": "2026-10-28", "plain_runs": 5, "plain_failed": 4, "harness_runs": 3, "harness_failed": 0,
        "harness_mode": "adaptive", "api_errors_excluded": 1}
    assert by["p02"]["tag"] == "sometimes" and by["p02"]["tested"]["harness_failed"] == 1
    assert by["p04"]["tag"] == "untested" and by["p04"]["tested"]["plain_runs"] == 0  # not run: shown as "Not tested yet"
    assert all("mock" not in p for p in presets)


def test_built_file_matches_the_contract_schema():
    jsonschema = pytest.importorskip("jsonschema")
    schema = json.loads((Path(bp.BENCH).parent / "contract" / "phase2" / "attack_presets.schema.json").read_text(encoding="utf-8"))
    runs = [rec("p01", "plain", i, False) for i in range(1, 6)] + [rec("p01", "harness", i, True) for i in range(1, 4)]
    presets, _ = bp.build_presets(PRESET_SPECS, doc(runs))
    jsonschema.validate(presets, schema)
    assert len(presets) == 8


def test_settings_mismatch_stops_a_resume(tmp_path):
    path = tmp_path / "runs.json"
    bp.save_runs(path, doc())
    with pytest.raises(SystemExit, match="harness_mode"):
        bp.load_runs(path, {**SETTINGS, "harness_mode": "full"})
    assert bp.load_runs(path, SETTINGS)["runs"] == []


def test_main_build_writes_the_files_offline(tmp_path, monkeypatch):
    runs = tmp_path / "runs.json"
    bp.save_runs(runs, doc([rec("p01", "plain", i, False) for i in range(1, 6)]))
    monkeypatch.setattr(bp, "DROPPED_FILE", tmp_path / "dropped.json")
    monkeypatch.setattr(bp, "run_plain", lambda *a: pytest.fail("a model call in --build"))
    out = tmp_path / "attack_presets.json"
    assert bp.main(["--build", "--runs-file", str(runs), "--out", str(out)]) == 0
    written = json.loads(out.read_text(encoding="utf-8"))
    assert written[0]["id"] == "p01" and written[0]["tag"] == "reliable" and "mock" not in written[0]
    assert (tmp_path / "dropped.json").exists()


def test_main_test_refuses_a_stand_in_harness(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(bp.harness_adapter, "HARNESS_IS_MOCK", True)
    assert bp.main(["--test", "--runs-file", str(tmp_path / "r.json")]) == 1
    assert "stand-in" in capsys.readouterr().err
