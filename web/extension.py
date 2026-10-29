"""Server side of the Chrome extension (registered by web/server.py). The extension sends selected text and a skill;
the model calls happen here, so the API key never leaves the server's .env.

  POST /extension/run  {skill_text, input}  -> NDJSON events (the same stream as skillcompiler.stream.ndjson_events)
  GET  /extension/ping                      -> {"ok": true, "mode": ...}, so the extension can tell "server off" from "server on"

Same caps as the arena: input <= 1500 characters, skill <= 6000 characters and <= 6 steps, one run at a time (a second one
gets HTTP 429), 240 s per run (EXTENSION_TIMEOUT). Nothing is logged or saved. The body must be application/json, which a web page on another
site cannot send without a CORS preflight that this server never answers, so only the extension (host permission) can call it.
"""
from __future__ import annotations

import json
import os
import re
import sys
import threading
from pathlib import Path

from flask import Blueprint, Response, jsonify, request, stream_with_context

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

MAX_INPUT = 1500
MAX_SKILL = 6000
MAX_STEPS = 6
RUN_TIMEOUT_S = float(os.environ.get("EXTENSION_TIMEOUT", 240))   # the free API can be slow: one step has taken over 40 s

try:
    from skillcompiler.stream import ndjson_events as EVENTS
except ImportError:  # pragma: no cover - only without the harness
    EVENTS = None
try:
    from tools.lint_skill import parse_steps as _parse_steps
except ImportError:  # pragma: no cover
    _parse_steps = None

bp = Blueprint("extension", __name__, url_prefix="/extension")
BUSY = threading.Lock()


def mode() -> str:
    return os.environ.get("EXTENSION_MODE", "adaptive")


def count_steps(skill_text: str) -> int:
    if _parse_steps is None:  # pragma: no cover
        return len(re.findall(r"(?m)^\s*\d+[.)]\s", skill_text))
    return len(_parse_steps(skill_text)[0])


@bp.get("/ping")
def ping():
    return jsonify(ok=True, mode=mode())


@bp.post("/run")
def run():
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        return jsonify(error="Send a JSON object with skill_text and input."), 400
    skill, text = body.get("skill_text"), body.get("input")
    if not isinstance(skill, str) or not skill.strip():
        return jsonify(error="The skill is empty."), 400
    if not isinstance(text, str) or not text.strip():
        return jsonify(error="No text was selected."), 400
    if len(text) > MAX_INPUT:
        return jsonify(error=f"The selection is {len(text)} characters; the limit is {MAX_INPUT}. Select less text."), 400
    if len(skill) > MAX_SKILL:
        return jsonify(error=f"The skill is {len(skill)} characters; the limit is {MAX_SKILL}."), 400
    steps = count_steps(skill)
    if steps > MAX_STEPS:
        return jsonify(error=f"The skill has {steps} steps; the limit is {MAX_STEPS}."), 400
    if EVENTS is None:
        return jsonify(error="The harness is not importable on this server."), 501
    if not BUSY.acquire(blocking=False):
        return jsonify(error="Another run is using the model right now. Try again in a minute."), 429

    def generate():
        try:
            yield from EVENTS(skill, text, mode=mode(), max_steps=MAX_STEPS, timeout_s=RUN_TIMEOUT_S)
        except Exception as exc:  # noqa: BLE001 - the stream must end with one error line, not a broken connection
            yield json.dumps({"type": "error", "message": f"{type(exc).__name__}: {exc}"}) + "\n"
        finally:
            BUSY.release()

    return Response(stream_with_context(generate()), mimetype="application/x-ndjson")
