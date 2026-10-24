import json

from skillcompiler import __main__ as cli
from skillcompiler import llm

SKILL = "---\nname: demo\n---\n1. Say the name.\n2. Say hi.\n"
PLAN = {"steps": [
    {"id": 1, "title": "Name", "instruction": "Say the name.", "output_format": "text",
     "expected_output": "", "depends_on": []},
    {"id": 2, "title": "Hi", "instruction": "Say hi.", "output_format": "text",
     "expected_output": "", "depends_on": [1]}]}


def fake(monkeypatch):
    def gen(prompt, model):
        if "precise parser" in prompt:
            return json.dumps(PLAN)
        if "Does the output follow" in prompt:
            return "PASS"
        return "Ravi" if "Step 1:" in prompt.split("Original input")[0] else "hi Ravi"
    monkeypatch.setattr(llm, "_generate", gen)


def test_compile_writes_plan(monkeypatch, tmp_path):
    fake(monkeypatch)
    skill = tmp_path / "SKILL.md"
    skill.write_text(SKILL, encoding="utf-8")
    out = tmp_path / "plan.json"
    assert cli.main(["compile", str(skill), "-o", str(out), "--model", "m"]) == 0
    plan = json.loads(out.read_text(encoding="utf-8"))
    assert plan["skill_name"] == "demo" and len(plan["steps"]) == 2


def test_run_writes_trace_and_prints_answer(monkeypatch, tmp_path, capsys):
    fake(monkeypatch)
    skill = tmp_path / "SKILL.md"
    skill.write_text(SKILL, encoding="utf-8")
    inp = tmp_path / "in.txt"
    inp.write_text("Hello from Ravi", encoding="utf-8")
    trace = tmp_path / "trace.json"
    code = cli.main(["run", str(skill), "--input-file", str(inp), "--trace", str(trace),
                     "--model", "m"])
    assert code == 0
    t = json.loads(trace.read_text(encoding="utf-8"))
    assert t["mode"] == "harness" and t["final_output"] == "hi Ravi"
    assert capsys.readouterr().out.strip().endswith("hi Ravi")


def test_missing_file_is_a_clean_error(capsys):
    assert cli.main(["run", "nope.md", "--input", "x"]) == 1
    assert "file not found" in capsys.readouterr().err
