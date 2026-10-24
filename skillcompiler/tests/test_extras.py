import json

import pytest

from skillcompiler import __main__ as cli
from skillcompiler import cache, llm
from skillcompiler.plan_io import load_plan, save_plan

PLAN = {"skill_name": "demo", "source_file": "x", "steps": [
    {"id": 1, "title": "Name", "instruction": "Say the name.", "output_format": "text",
     "expected_output": "", "depends_on": []},
    {"id": 2, "title": "Hi", "instruction": "Say hi.", "output_format": "one_of:a|b",
     "expected_output": "", "depends_on": [1]}]}
SKILL = "---\nname: demo\n---\n1. Say the name.\n2. Say hi.\n"


@pytest.fixture(autouse=True)
def reset_cache():
    yield
    cache.configure(enabled=False)


@pytest.mark.parametrize("name", ["plan.json", "plan.yaml", "plan.yml"])
def test_plan_roundtrip(tmp_path, name):
    save_plan(PLAN, tmp_path / name)
    assert load_plan(tmp_path / name) == PLAN


@pytest.mark.parametrize("text", ["not json", "[]", '{"steps": []}', '{"nope": 1}'])
def test_load_plan_rejects_bad_files(tmp_path, text):
    (tmp_path / "p.json").write_text(text, encoding="utf-8")
    with pytest.raises(ValueError):
        load_plan(tmp_path / "p.json")


def counting_api(monkeypatch):
    calls = []

    def gen(prompt, model):
        calls.append(prompt)
        if "Does the output follow" in prompt:
            return "PASS"
        return "a" if "Step 2:" in prompt.split("Original input")[0] else "Ravi"

    monkeypatch.setattr(llm, "_generate", gen)
    return calls


def test_cache_second_run_makes_zero_api_calls(monkeypatch, tmp_path):
    calls = counting_api(monkeypatch)
    cache.configure(enabled=True, directory=tmp_path / "c")
    from skillcompiler import run_skill
    first = run_skill("", "in", plan=PLAN, model="m")
    n = len(calls)
    assert n == 4 and first["totals"]["cache_hits"] == 0
    second = run_skill("", "in", plan=PLAN, model="m")
    assert len(calls) == n  # no new API calls
    assert second["totals"] == {"llm_calls": 0, "latency_ms": 0, "retries": 0, "cache_hits": 4}
    assert second["final_output"] == first["final_output"]


def test_replay_miss_is_a_clear_error(monkeypatch, tmp_path):
    counting_api(monkeypatch)
    cache.configure(replay=True, directory=tmp_path / "empty")
    with pytest.raises(cache.CacheMiss, match="--cache"):
        llm.call_llm("anything", model="m")


def test_cache_off_by_default(monkeypatch, tmp_path):
    calls = counting_api(monkeypatch)
    llm.call_llm("p", model="m")
    llm.call_llm("p", model="m")
    assert len(calls) == 2


def test_cli_compile_yaml_then_run_with_plan_and_replay(monkeypatch, tmp_path, capsys):
    calls = counting_api(monkeypatch)
    skill = tmp_path / "SKILL.md"
    skill.write_text(SKILL, encoding="utf-8")
    plan = tmp_path / "plan.yaml"
    save_plan(PLAN, plan)
    base = ["run", str(skill), "--input", "hello", "--plan", str(plan), "--model", "m",
            "--cache-dir", str(tmp_path / "c")]
    assert cli.main(base + ["--cache"]) == 0
    online = len(calls)
    assert cli.main(base + ["--replay"]) == 0
    assert len(calls) == online
    assert "cache hits" in capsys.readouterr().err


def test_cli_replay_miss_exits_cleanly(monkeypatch, tmp_path, capsys):
    counting_api(monkeypatch)
    skill = tmp_path / "SKILL.md"
    skill.write_text(SKILL, encoding="utf-8")
    plan = tmp_path / "plan.json"
    save_plan(PLAN, plan)
    code = cli.main(["run", str(skill), "--input", "x", "--plan", str(plan), "--model", "m",
                     "--replay", "--cache-dir", str(tmp_path / "none")])
    assert code == 1 and "not in the cache" in capsys.readouterr().err
