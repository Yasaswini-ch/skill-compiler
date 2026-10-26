"""Prototype live server: streams a harness run as newline-delimited JSON.

    python server.py            # needs the repo's Python deps and its .env; serves http://127.0.0.1:5001

Endpoints
  GET  /presets      -> the example skills with their inputs
  POST /run-stream   {"skill_text", "input", "verify"?} -> application/x-ndjson, one event per line
"""
import sys
from pathlib import Path

from flask import Flask, Response, jsonify, request, stream_with_context

ROOT = Path(__file__).resolve().parents[3]  # the repo root
sys.path.insert(0, str(ROOT))

from skillcompiler.stream import ndjson_events  # noqa: E402

app = Flask(__name__)


@app.after_request
def cors(response):
    # The page may be opened from a folder (file://), whose origin is "null".
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    return response


@app.get("/presets")
def presets():
    out = []
    for d in sorted((ROOT / "skillcompiler" / "examples").iterdir()):
        if (d / "SKILL.md").exists() and (d / "input.txt").exists():
            out.append({"name": d.name, "skill_text": (d / "SKILL.md").read_text(encoding="utf-8"),
                        "input": (d / "input.txt").read_text(encoding="utf-8").strip()})
    return jsonify(out)


@app.route("/run-stream", methods=["POST", "OPTIONS"])
def run_stream():
    if request.method == "OPTIONS":
        return ("", 204)
    body = request.get_json(silent=True) or {}
    skill, text = body.get("skill_text", ""), body.get("input", "")
    if not skill.strip() or not text.strip():
        return jsonify(error="skill_text and input are both required"), 400
    kwargs = {} if body.get("verify") is None else {"verify": bool(body["verify"])}
    events = ndjson_events(skill, text, **kwargs)
    return Response(stream_with_context(events), mimetype="application/x-ndjson",
                    headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"})


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5001, threaded=True)
