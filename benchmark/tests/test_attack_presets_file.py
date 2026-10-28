"""Tests of the finished benchmark/attack_presets.json: it must match the contract and be traceable to the saved runs."""
import json
from pathlib import Path

import pytest

from benchmark import build_presets as bp
from benchmark.presets_src import PRESET_SPECS

BENCH = Path(__file__).resolve().parents[1]
PRESETS = json.loads((BENCH / "attack_presets.json").read_text(encoding="utf-8"))
RUNS = json.loads((BENCH / "output" / "presets" / "runs.json").read_text(encoding="utf-8"))
DROPPED = json.loads((BENCH / "output" / "presets" / "dropped_presets.json").read_text(encoding="utf-8"))
SPECS = {p["id"]: p for p in PRESET_SPECS}


def test_matches_the_contract_schema():
    jsonschema = pytest.importorskip("jsonschema")
    schema = json.loads((BENCH.parent / "contract" / "phase2" / "attack_presets.schema.json").read_text(encoding="utf-8"))
    jsonschema.validate(PRESETS, schema)


def test_real_presets_are_not_marked_mock_and_are_all_tested():
    for p in PRESETS:
        assert "mock" not in p, p["id"]  # a mock preset is never counted by the arena
        assert p["tag"] in ("reliable", "sometimes") and p["tested"]["plain_runs"] > 0


def test_every_preset_comes_from_the_source_unchanged():
    for p in PRESETS:
        s = SPECS[p["id"]]
        assert {k: p[k] for k in ("title", "skill_text", "input", "checks", "steps", "why_it_breaks")} == \
               {k: s[k] for k in ("title", "skill_text", "input", "checks", "steps", "why_it_breaks")}, p["id"]


def test_tested_counts_and_tags_are_recomputed_from_the_saved_runs():
    rebuilt, dropped = bp.build_presets(PRESET_SPECS, RUNS)
    assert rebuilt == PRESETS
    assert dropped == DROPPED


def test_dropped_presets_are_exactly_those_plain_never_failed():
    kept = {p["id"] for p in PRESETS}
    dropped = {d["id"] for d in DROPPED}
    assert kept | dropped == set(SPECS) and not kept & dropped
    for d in DROPPED:
        assert d["plain_failed"] == 0 and d["plain_runs"] > 0


def test_counts_exclude_api_errors_and_the_runs_file_is_sane():
    s = RUNS["settings"]
    assert s["harness_is_mock"] is False and s["provider"] == "gemini" and s["verifier"] == "on"
    for p in PRESETS:
        runs = [r for r in RUNS["runs"] if r["preset_id"] == p["id"]]
        assert p["tested"]["api_errors_excluded"] == sum(r["api_error"] for r in runs)
    for r in RUNS["runs"]:
        if r["api_error"]:
            # either the model call itself failed (no score), or a harness run FAILED after an attempt hit an API error;
            # both are kept in the file for transparency and neither is counted
            assert r["passed"] is None or (r["mode"] == "harness" and r["passed"] is False and r["api_errors_in_run"] > 0)
        else:
            assert r["passed"] in (True, False)


def test_the_arena_loads_the_file():
    pytest.importorskip("flask")
    from web import arena
    loaded = arena.load_presets()
    assert [p["id"] for p in loaded] == [p["id"] for p in PRESETS]
    assert not any(p.get("mock") for p in loaded)
    public = [arena.public_preset(p) for p in loaded]
    assert all("checks" not in p for p in public)  # the checks are never sent to the browser
