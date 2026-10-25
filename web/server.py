"""Judge live mode: serves the pages in web/ and runs a skill plain vs harness.

Usage (from the repo root): python web/server.py   then open http://127.0.0.1:5000/live.html

Endpoints
  POST /run      {"skill_text", "input", "mode": "plain"|"harness"} -> trace.json dict
  POST /lint     {"skill_text"} -> lint report
  GET  /recorded -> recorded plain + harness traces (no API call)
  GET  /presets  -> sample skills with inputs
Adapters: the real harness / plain runner when importable, otherwise a stand-in whose
traces carry "mock": true, and the page shows a red MOCK banner.
"""
import copy
import json
import sys
from pathlib import Path

from flask import Flask, jsonify, request, send_from_directory

WEB = Path(__file__).resolve().parent
ROOT = WEB.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import lint_skill  # noqa: E402


def _canned(name: str) -> dict:
    return json.loads((WEB / "mock" / name).read_text(encoding="utf-8"))


try:
    from skillcompiler import run_skill
    HARNESS_IS_MOCK = False
except ImportError as e:
    HARNESS_IS_MOCK = True
    print(f"WARNING: skillcompiler not importable ({e}), /run harness uses a canned MOCK trace.")

    def run_skill(skill_text, user_input, model=None):
        t = copy.deepcopy(_canned("trace.json"))
        t.update(mock=True, mode="harness", input=user_input)
        return t

try:
    from benchmark.run_plain import run_plain
    PLAIN_IS_MOCK = False
except ImportError as e:
    PLAIN_IS_MOCK = True
    print(f"WARNING: benchmark.run_plain not importable ({e}), /run plain uses a canned MOCK trace.")

    def run_plain(skill_text, user_input, model=None):
        t = copy.deepcopy(_canned("trace_plain.json"))
        t["input"] = user_input
        return t

app = Flask(__name__, static_folder=None)


@app.get("/")
def home():
    return send_from_directory(WEB, "index.html")


@app.get("/<path:name>")
def static_files(name):
    return send_from_directory(WEB, name)


@app.post("/run")
def run():
    body = request.get_json(silent=True) or {}
    skill, text, mode = body.get("skill_text", ""), body.get("input", ""), body.get("mode")
    if not skill.strip() or not text.strip():
        return jsonify(error="skill_text and input are both required"), 400
    if mode not in ("plain", "harness"):
        return jsonify(error='mode must be "plain" or "harness"'), 400
    try:
        trace = run_plain(skill, text) if mode == "plain" else run_skill(skill, text)
    except Exception as e:  # missing key, model name, network: tell the page, do not crash the server
        return jsonify(error=f"{type(e).__name__}: {e}"), 500
    return jsonify(trace)


@app.post("/lint")
def lint():
    body = request.get_json(silent=True) or {}
    return jsonify(lint_skill.lint(body.get("skill_text", "")))


@app.get("/recorded")
def recorded():
    return jsonify(plain=_canned("trace_plain.json"), harness=_canned("trace.json"))


@app.get("/presets")
def presets():
    out = []
    for name in ("ticket-triage", "meeting-minutes"):
        d = ROOT / "skillcompiler" / "examples" / name
        if (d / "SKILL.md").exists():
            out.append({"name": name, "skill_text": (d / "SKILL.md").read_text(encoding="utf-8"),
                        "input": (d / "input.txt").read_text(encoding="utf-8") if (d / "input.txt").exists() else ""})
    return jsonify(out)


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, threaded=True)
