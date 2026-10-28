"""Tests for run_plain, harness_adapter and run_compare with fake model calls (no API key)."""
import json

import pytest

from benchmark import client, harness_adapter, run_compare as rc, run_plain as rp
from benchmark.tests.golden import GOLDEN

TASKS = rp.load_tasks()


def fake_trace(mode, output, mock=False, calls=1):
    return {"run_id": "r", "mode": mode, "mock": mock, "model": "m", "skill": "s", "input": "i",
            "steps": [{"step_id": 1, "title": "t", "status": "repaired", "attempts": []}] if mode == "harness" else [],
            "final_output": output, "totals": {"llm_calls": calls, "latency_ms": 10, "retries": 1 if mode == "harness" else 0}}


@pytest.fixture
def env(monkeypatch, tmp_path):
    monkeypatch.setenv("GEMMA_MODEL", "m1")
    monkeypatch.delenv("GEMMA_THINKING", raising=False)
    monkeypatch.delenv("SKILLCOMPILER_VERIFY", raising=False)
    monkeypatch.setattr(rc.time, "sleep", lambda s: None)
    monkeypatch.setattr(rc.harness_adapter, "HARNESS_IS_MOCK", False)
    return tmp_path


def patch_runners(monkeypatch, plain_out, harness_out):
    """plain_out / harness_out: function(task_id) -> output text."""
    by_input = {t["input"]: t["task_id"] for t in TASKS}
    monkeypatch.setattr(rc, "run_plain", lambda s, i, m=None: fake_trace("plain", plain_out(by_input[i])))
    monkeypatch.setattr(rc.harness_adapter, "run_skill",
                        lambda s, i, m=None: fake_trace("harness", harness_out(by_input[i], ), calls=7))


def good(tid):
    return GOLDEN[tid]["good"][0]


def bad(tid):
    return GOLDEN[tid]["bad"][0][0]


def test_plain_prompt_is_skill_then_input_only():
    p = rp.plain_prompt("SKILL TEXT\n", "my input\n")
    assert p == "SKILL TEXT\n\nInput:\nmy input"


def test_run_plain_builds_contract_trace(monkeypatch):
    monkeypatch.setenv("GEMMA_MODEL", "m1")
    seen = []
    monkeypatch.setattr(client, "call_llm", lambda prompt, model=None: seen.append(prompt) or "out")
    client.stats.reset()
    tr = rp.run_plain("---\nname: demo-skill\n---\n1. x", "hello")
    assert tr["mode"] == "plain" and tr["mock"] is False and tr["steps"] == []
    assert tr["skill"] == "demo-skill" and tr["final_output"] == "out" and tr["input"] == "hello"
    assert set(tr["totals"]) >= {"llm_calls", "latency_ms", "retries"}
    assert len(seen) == 1


def test_adapter_uses_real_harness_when_import_works():
    # skillcompiler is in this repo, so the import must succeed and the flag must be False
    assert harness_adapter.IMPORT_ERROR is None
    assert harness_adapter.HARNESS_IS_MOCK is False


def test_stand_in_is_flagged_mock(monkeypatch):
    """Simulate a missing skillcompiler by reloading the adapter with the import blocked."""
    import builtins
    import importlib
    import sys

    real_import = builtins.__import__

    def blocked(name, *a, **k):
        if name == "skillcompiler" or name.startswith("skillcompiler."):
            raise ImportError("blocked for test")
        return real_import(name, *a, **k)

    saved = {k: v for k, v in sys.modules.items() if k.startswith("skillcompiler")}
    for k in saved:
        del sys.modules[k]
    monkeypatch.setattr(builtins, "__import__", blocked)
    try:
        mod = importlib.reload(harness_adapter)
        assert mod.HARNESS_IS_MOCK is True and "blocked for test" in mod.IMPORT_ERROR
        monkeypatch.setattr(mod, "run_plain", lambda s, i, m=None: fake_trace("plain", "x"))
        tr = mod.run_skill("s", "i")
        assert tr["mode"] == "harness" and tr["mock"] is True
    finally:
        monkeypatch.undo()
        sys.modules.update(saved)
        importlib.reload(harness_adapter)


def test_verifier_setting(monkeypatch):
    monkeypatch.delenv("SKILLCOMPILER_VERIFY", raising=False)
    assert harness_adapter.verifier_setting() == "on"
    monkeypatch.setenv("SKILLCOMPILER_VERIFY", "0")
    assert harness_adapter.verifier_setting() == "off"


def test_full_run_writes_contract_files(env, monkeypatch):
    # plain fails t01 and t02, passes the rest; harness passes everything
    patch_runners(monkeypatch, lambda t: bad(t) if t in ("t01", "t02") else good(t), good)
    out = env / "out"
    assert rc.main(["--out-dir", str(out), "--sleep", "0"]) == 0
    res = json.loads((out / "results.json").read_text(encoding="utf-8"))
    assert res["summary"] == {"plain": {"passed": 8, "total": 10}, "harness": {"passed": 10, "total": 10}}
    assert res["harness_is_mock"] is False
    assert res["gemma_thinking"] == "MINIMAL" and res["verifier"] == "on" and res["cache_used"] is False
    assert res["model"] == "m1" and len(res["tasks"]) == 10
    t01 = res["tasks"][0]
    assert t01["task_id"] == "t01" and t01["plain"]["passed"] is False and t01["harness"]["passed"] is True
    assert t01["plain"]["failure_label"] and t01["harness"]["failure_label"] is None
    assert {"passed", "failed_checks", "failure_label", "llm_calls", "latency_ms", "output_excerpt"} <= set(t01["plain"])
    assert t01["harness"]["llm_calls"] == 7 and t01["harness"]["steps"]["repaired"] == 1
    fails = json.loads((out / "failures.json").read_text(encoding="utf-8"))
    assert [f["task_id"] for f in fails] == ["t01", "t02"] and all(f["mode"] == "plain" for f in fails)
    assert fails[0]["failure_id"] == "f001" and fails[0]["what_went_wrong"] and len(fails[0]["output_excerpt"]) <= 300
    assert (out / "traces" / "t01_plain.json").exists() and (out / "traces" / "t01_harness.json").exists()


def test_mock_flag_and_verifier_off_are_recorded(env, monkeypatch):
    monkeypatch.setattr(rc.harness_adapter, "HARNESS_IS_MOCK", True)
    monkeypatch.setattr(rc.harness_adapter, "IMPORT_ERROR", "ImportError('x')")
    patch_runners(monkeypatch, good, good)
    out = env / "out"
    rc.main(["--out-dir", str(out), "--sleep", "0", "--limit", "2", "--no-verify"])
    res = json.loads((out / "results.json").read_text(encoding="utf-8"))
    assert res["harness_is_mock"] is True and res["verifier"] == "off"
    monkeypatch.delenv("SKILLCOMPILER_VERIFY", raising=False)


def test_limit_and_resume(env, monkeypatch):
    patch_runners(monkeypatch, good, good)
    out = env / "out"
    rc.main(["--out-dir", str(out), "--sleep", "0", "--limit", "3"])
    assert len(json.loads((out / "results.json").read_text())["tasks"]) == 3
    calls = []
    by_input = {t["input"]: t["task_id"] for t in TASKS}
    monkeypatch.setattr(rc, "run_plain", lambda s, i, m=None: calls.append(by_input[i]) or fake_trace("plain", good(by_input[i])))
    rc.main(["--out-dir", str(out), "--sleep", "0", "--resume"])
    res = json.loads((out / "results.json").read_text())
    assert len(res["tasks"]) == 10 and "t01" not in calls and calls[0] == "t04"
    assert [t["task_id"] for t in res["tasks"]] == sorted(t["task_id"] for t in res["tasks"])


def test_resume_refuses_mixed_settings(env, monkeypatch):
    patch_runners(monkeypatch, good, good)
    out = env / "out"
    rc.main(["--out-dir", str(out), "--sleep", "0", "--limit", "1"])
    monkeypatch.setenv("GEMMA_THINKING", "default")
    with pytest.raises(SystemExit, match="mix settings"):
        rc.main(["--out-dir", str(out), "--sleep", "0", "--resume"])


def test_api_error_task_is_not_recorded(env, monkeypatch):
    patch_runners(monkeypatch, good, good)

    def flaky(s, i, m=None):
        if "Brightwell" in i:
            raise RuntimeError("LLM call failed after 3 tries")
        return fake_trace("plain", good({t["input"]: t["task_id"] for t in TASKS}[i]))

    monkeypatch.setattr(rc, "run_plain", flaky)
    out = env / "out"
    rc.main(["--out-dir", str(out), "--sleep", "0"])
    ids = [t["task_id"] for t in json.loads((out / "results.json").read_text())["tasks"]]
    assert len(ids) == 9 and "t04" not in ids


def test_failure_entries_for_both_modes():
    task = TASKS[0]
    cell_fail = rc.mode_entry(task, fake_trace("plain", "not json"))
    cell_pass = rc.mode_entry(task, fake_trace("harness", GOLDEN["t01"]["good"][0]))
    fails = rc.build_failures([{"task_id": "t01", "title": "x", "plain": cell_fail, "harness": cell_pass}])
    assert len(fails) == 1 and fails[0]["label"] == "wrong_format" and "c1" in fails[0]["what_went_wrong"]


def test_label_overrides_file_is_valid():
    ov = rc.load_overrides()
    labels = {"skipped_step", "wrong_format", "lost_track", "merged_steps", "hallucinated_step",
              "ignored_constraint", "other"}
    ids = {t["task_id"] for t in TASKS}
    assert set(ov) <= ids
    for entry in ov.values():
        assert entry["label"] in labels and entry["reason"] and entry.get("mode", "plain") in rc.MODES
    assert ov["t04"]["label"] == ov["t05"]["label"] == "other"
    assert ov["t04"]["reason"] == "arithmetic error: wrong subtotal, later steps follow it"
    assert ov["t08"]["label"] == "wrong_format"


def test_apply_override_changes_label_only_for_failed_cells_of_the_named_mode():
    ov = {"t04": {"mode": "plain", "label": "other", "reason": "why"}, "t08": {"label": "wrong_format", "reason": "r"}}
    failed = {"passed": False, "failure_label": "lost_track", "failed_checks": ["c4"], "details": {"c4": "x"}}
    done = rc.apply_override("t04", "plain", failed, ov)
    assert done["failure_label"] == "other" and done["scorer_label"] == "lost_track" and done["label_note"] == "why"
    assert rc.apply_override("t04", "harness", failed, ov) == failed           # override is plain-only
    assert rc.apply_override("t08", "harness", failed, ov)["failure_label"] == "wrong_format"  # no mode = both
    passed = {**failed, "passed": True, "failure_label": None}
    assert rc.apply_override("t04", "plain", passed, ov) == passed             # passing cells are untouched
    assert rc.apply_override("t01", "plain", failed, ov) == failed


def test_run_compare_applies_overrides_but_keeps_real_reason(env, monkeypatch):
    wrong_t04 = json.dumps({**json.loads(good("t04")), "subtotal": "171.75"})
    patch_runners(monkeypatch, lambda t: wrong_t04 if t == "t04" else good(t), lambda t: wrong_t04 if t == "t04" else good(t))
    out = env / "out"
    rc.main(["--out-dir", str(out), "--sleep", "0"])
    res = json.loads((out / "results.json").read_text(encoding="utf-8"))
    t04 = next(t for t in res["tasks"] if t["task_id"] == "t04")
    assert t04["plain"]["failure_label"] == "other" and t04["plain"]["scorer_label"] == "lost_track"
    assert t04["harness"]["failure_label"] == "lost_track" and "label_note" not in t04["harness"]  # plain-only override
    fails = {(f["task_id"], f["mode"]): f for f in json.loads((out / "failures.json").read_text(encoding="utf-8"))}
    plain = fails[("t04", "plain")]
    assert plain["label"] == "other" and plain["label_note"].startswith("arithmetic error")
    assert "c4" in plain["what_went_wrong"] and "did not match" in plain["what_went_wrong"]  # real reason kept
    assert fails[("t04", "harness")]["label"] == "lost_track"
