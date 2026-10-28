"""Break Gemma Arena, server side. Registered by web/server.py (`app.register_blueprint(arena.bp)`).

People try to make plain Gemma fail while the harness runs beside it. Two honest modes:
  * preset ("challenge"): a tested challenge. benchmark/scorer.py scores BOTH answers with the preset's checks.
    Only these can count towards the failure counter, and only when plain failed.
  * free: any instructions. Both outputs are shown and marked UNVERIFIED; nothing is scored or counted.

Endpoints
  GET  /arena/presets             tested challenges (checks are not sent)
  POST /arena/join                {nickname, kind, preset_id, skill_text, input, consent} -> {attempt_id, position, estimated_wait_s}
  GET  /arena/stream/<attempt_id> NDJSON: queue updates, then start, plain, the harness events, scored
  GET  /arena/stats               {failures_collected, attempts, leaderboard, queue_length, mode, provider, mock}

Rules kept here: consent required; input <= 1500 characters; skill <= 6000 characters and <= 6 steps; <= 5 attempts per
nickname; one run at a time (FIFO); an attempt whose page disconnects is dropped; nothing is logged but the nickname and the
text (no names, emails or IP addresses). arena_log.jsonl and arena_traces/ hold attendee text and are gitignored.
"""
from __future__ import annotations

import json
import os
import re
import sys
import threading
import time
from collections import Counter
from pathlib import Path

from flask import Blueprint, Response, jsonify, request, stream_with_context

WEB = Path(__file__).resolve().parent
ROOT = WEB.parent
sys.path.insert(0, str(ROOT))

MAX_INPUT = 1500
MAX_SKILL = 6000
MAX_STEPS = 6
MAX_ATTEMPTS_PER_NICKNAME = 5
RUN_TIMEOUT_S = 150
CONNECT_TTL_S = 25  # an attempt that joined but never opened its stream is dropped after this long
NICKNAME_RE = re.compile(r"^[A-Za-z0-9 _.\-]{1,20}$")

# ---- adapters: the real thing when importable, otherwise a stand-in that marks its results MOCK ----------------------
STANDIN_REASONS: list[str] = []

try:
    from skillcompiler.stream import ndjson_events as _real_events
    from skillcompiler import llm as _llm, providers as _providers
except ImportError as exc:  # pragma: no cover - only without the harness
    _real_events = _llm = _providers = None
    STANDIN_REASONS.append(f"harness not importable ({exc})")

try:
    from benchmark.run_plain import run_plain as _real_plain
except ImportError as exc:  # pragma: no cover
    _real_plain = None
    STANDIN_REASONS.append(f"benchmark.run_plain not importable ({exc})")

try:
    from benchmark.scorer import score_output as _real_score
except ImportError as exc:  # pragma: no cover
    _real_score = None
    STANDIN_REASONS.append(f"benchmark.scorer not importable ({exc})")

try:
    from tools.lint_skill import parse_steps as _parse_steps
except ImportError:  # pragma: no cover
    _parse_steps = None


def _standin_events(skill_text: str, user_input: str, **_: object):  # pragma: no cover
    for line in (WEB / "mock" / "events_repair.ndjson").read_text(encoding="utf-8").splitlines():
        time.sleep(0.4)
        event = json.loads(line)
        if event["type"] == "run_end":
            event["trace"]["mock"] = True
        yield json.dumps(event) + "\n"


def _standin_plain(skill_text: str, user_input: str, model: str | None = None) -> dict:  # pragma: no cover
    return {"final_output": "(stand-in: plain Gemma is not connected)", "mock": True, "steps": [], "totals": {"llm_calls": 0}}


def _standin_score(task: dict, output: str) -> dict:  # pragma: no cover
    return {"passed": False, "failed_checks": [task["checks"][0]["id"]], "failure_label": "other",
            "details": {task["checks"][0]["id"]: "stand-in scorer"}}


# Replaceable by tests.
EVENTS = _real_events or _standin_events
PLAIN = _real_plain or _standin_plain
SCORE = _real_score or _standin_score


def standin_in_use() -> bool:
    return EVENTS is _standin_events or PLAIN is _standin_plain or SCORE is _standin_score


# ---- settings from the environment ------------------------------------------------------------------------------------
def harness_mode() -> str:
    """The harness mode the arena uses (shown on screen). Adaptive keeps runs short; ARENA_MODE=full for the full verifier."""
    return os.environ.get("ARENA_MODE", "adaptive")


def local_provider() -> bool:
    return os.environ.get("ARENA_PROVIDER", "gemini").lower() == "local"


def provider_label() -> str:
    if local_provider():
        return f"LOCAL MODEL ({os.environ.get('ARENA_MODEL', 'unnamed')})"
    return "Gemini API"


def configure_provider() -> None:
    """ARENA_PROVIDER=local points the harness at a local OpenAI-compatible server (Ollama), so the arena works offline."""
    if local_provider() and _providers is not None:
        _providers.configure("openai-compatible", os.environ.get("ARENA_BASE_URL", "http://localhost:11434/v1"))


def _model_kwargs() -> dict:
    model = os.environ.get("ARENA_MODEL")
    return {"model": model} if model else {}


def _plain_call(skill_text: str, user_input: str) -> dict:
    if local_provider() and _llm is not None:  # the benchmark's plain runner is Gemini-only
        output = _llm.call_llm(f"{skill_text.strip()}\n\nInput:\n{user_input.strip()}", **_model_kwargs())
        return {"final_output": output, "mock": False}
    return PLAIN(skill_text, user_input)


# ---- presets ---------------------------------------------------------------------------------------------------------
def preset_files() -> list[Path]:
    env = os.environ.get("ARENA_PRESETS")
    return ([Path(env)] if env else []) + [ROOT / "benchmark" / "attack_presets.json",
                                         ROOT / "contract" / "phase2" / "attack_presets.json"]


def load_presets() -> list[dict]:
    for path in preset_files():
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    return []


def public_preset(p: dict) -> dict:
    keys = ("id", "title", "tag", "why_it_breaks", "steps", "skill_text", "input", "tested", "mock")
    out = {k: p[k] for k in keys if k in p}
    out["n_checks"] = len(p.get("checks", []))
    return out


def count_steps(skill_text: str) -> int:
    if _parse_steps is None:  # pragma: no cover
        return len(re.findall(r"(?m)^\s*\d+[.)]\s", skill_text))
    return len(_parse_steps(skill_text)[0])


def _line(event: dict) -> str:
    return json.dumps(event, ensure_ascii=False) + "\n"


# ---- the arena -------------------------------------------------------------------------------------------------------
class Arena:
    def __init__(self, log_path: Path | None = None, trace_dir: Path | None = None, clock=time.monotonic):
        self.log_path = log_path or Path(os.environ.get("ARENA_LOG", WEB / "arena_log.jsonl"))
        self.trace_dir = trace_dir or Path(os.environ.get("ARENA_TRACES", WEB / "arena_traces"))
        self.clock = clock
        self.cond = threading.Condition()
        self.attempts: dict[str, dict] = {}
        self.order: list[str] = []      # attempts that have joined and not finished, oldest first
        self.running: str | None = None
        self.per_nickname: Counter = Counter()
        self.avg_run_s = 60.0
        self.counter = self._count_log_rows()
        self.next_id = self._highest_logged_id()

    # -- joining ----------------------------------------------------------------------------------------------------
    def join(self, body: object) -> tuple[dict, int]:
        if not isinstance(body, dict):
            return {"error": "body must be a JSON object"}, 400
        if body.get("consent") is not True:
            return {"error": "Please tick the box: your text is sent to Google's Gemini API and may be kept in a public dataset after review."}, 400
        nickname = body.get("nickname")
        if not isinstance(nickname, str) or not NICKNAME_RE.match(nickname.strip()):
            return {"error": "Nickname: 1 to 20 letters, digits, spaces or . _ - (please not your real name)."}, 400
        nickname = nickname.strip()
        kind = body.get("kind")
        if kind not in ("preset", "free"):
            return {"error": 'kind must be "preset" or "free"'}, 400
        user_input = body.get("input")
        if not isinstance(user_input, str) or not user_input.strip():
            return {"error": "The input is empty."}, 400
        if len(user_input) > MAX_INPUT:
            return {"error": f"The input is {len(user_input)} characters; the limit is {MAX_INPUT}."}, 400
        preset = None
        if kind == "preset":
            preset = next((p for p in load_presets() if p.get("id") == body.get("preset_id")), None)
            if preset is None:
                return {"error": "Unknown challenge."}, 400
            skill_text = preset["skill_text"]
        else:
            skill_text = body.get("skill_text")
            if not isinstance(skill_text, str) or not skill_text.strip():
                return {"error": "The skill text is empty."}, 400
            if len(skill_text) > MAX_SKILL:
                return {"error": f"The skill is {len(skill_text)} characters; the limit is {MAX_SKILL}."}, 400
            steps = count_steps(skill_text)
            if steps > MAX_STEPS:
                return {"error": f"The skill has {steps} steps; the limit is {MAX_STEPS}."}, 400
        with self.cond:
            self._drop_stale()
            if self.per_nickname[nickname] >= MAX_ATTEMPTS_PER_NICKNAME:
                return {"error": f"That nickname has used its {MAX_ATTEMPTS_PER_NICKNAME} attempts."}, 400
            self.per_nickname[nickname] += 1
            self.next_id += 1
            attempt_id = f"a-{self.next_id:04d}"
            self.attempts[attempt_id] = {"id": attempt_id, "nickname": nickname, "kind": kind, "preset": preset,
                                         "preset_id": preset["id"] if preset else None, "skill_text": skill_text,
                                         "input": user_input, "status": "joined", "joined": self.clock()}
            self.order.append(attempt_id)
            position, wait = self._position(attempt_id)
        return {"attempt_id": attempt_id, "position": position, "estimated_wait_s": wait,
                "mode": harness_mode(), "provider": provider_label()}, 200

    # -- the queue ---------------------------------------------------------------------------------------------------
    def _position(self, attempt_id: str) -> tuple[int, int]:
        ahead = self.order.index(attempt_id)
        return ahead + 1, int(ahead * self.avg_run_s + (self.avg_run_s / 2 if self.running else 0))

    def _drop_stale(self) -> None:
        """Remove attempts that joined but never connected, so a closed tab cannot block the line."""
        now = self.clock()
        for aid in list(self.order):
            a = self.attempts[aid]
            if a["status"] == "joined" and now - a["joined"] > CONNECT_TTL_S:
                a["status"] = "dropped"
                self.order.remove(aid)
        self.cond.notify_all()

    def queue_length(self) -> int:
        with self.cond:
            self._drop_stale()
            return len(self.order)

    # -- running one attempt ----------------------------------------------------------------------------------------
    def stream(self, attempt_id: str):
        a = self.attempts.get(attempt_id)
        if a is None:
            yield _line({"type": "error", "message": "Unknown attempt."})
            return
        with self.cond:
            usable = a["status"] == "joined"
            if usable:
                a["status"] = "waiting"
        if not usable:
            yield _line({"type": "error", "message": "This attempt was dropped or already used. Join again."})
            return
        finished = False
        try:
            while True:  # wait for our turn: first in line and nobody running
                with self.cond:
                    self._drop_stale()
                    if self.order and self.order[0] == attempt_id and self.running is None:
                        self.running, a["status"] = attempt_id, "running"
                        break
                    position, wait = self._position(attempt_id) if attempt_id in self.order else (0, 0)
                yield _line({"type": "queue", "position": position, "estimated_wait_s": wait})
                with self.cond:
                    self.cond.wait(timeout=1.0)
            started = self.clock()
            yield from self._run(a)
            self.avg_run_s = 0.6 * self.avg_run_s + 0.4 * max(1.0, self.clock() - started)
            finished = True
        finally:  # runs on normal end, on error, and when the page disconnects (GeneratorExit)
            with self.cond:
                if attempt_id in self.order:
                    self.order.remove(attempt_id)
                if self.running == attempt_id:
                    self.running = None
                if not finished:
                    a["status"] = "dropped"
                else:
                    a["status"] = "done"
                self.cond.notify_all()

    def _run(self, a: dict):
        preset = a["preset"]
        standin = standin_in_use() or bool(preset and preset.get("mock"))  # a mock challenge has made-up checks: never counted
        yield _line({"type": "start", "attempt_id": a["id"], "kind": a["kind"], "mode": harness_mode(),
                     "provider": provider_label(), "mock": standin})
        plain_text, plain_error = "", None
        try:
            plain_text = str(_plain_call(a["skill_text"], a["input"]).get("final_output", ""))
        except Exception as exc:  # noqa: BLE001 - an API failure is not a model failure
            plain_error = f"{type(exc).__name__}: {exc}"
        plain = self._score_side(preset, plain_text) if plain_error is None else {"output": "", "passed": None, "failed_checks": [], "error": plain_error}
        yield _line({"type": "plain", "result": plain})

        trace, harness_error = None, None
        events = EVENTS(a["skill_text"], a["input"], mode=harness_mode(), max_steps=MAX_STEPS, timeout_s=RUN_TIMEOUT_S, **_model_kwargs())
        try:
            for chunk in events:
                event = json.loads(chunk)
                if event["type"] == "run_end":
                    trace = event["trace"]
                elif event["type"] == "error":
                    harness_error = event["message"]
                yield chunk
        finally:
            close = getattr(events, "close", None)
            if close:
                close()
        harness = (self._score_side(preset, trace["final_output"]) if trace and not harness_error
                   else {"output": (trace or {}).get("final_output", ""), "passed": None, "failed_checks": [], "error": harness_error or "no result"})
        broke_plain = None if (a["kind"] == "free" or plain.get("passed") is None) else (plain["passed"] is False)
        counted = bool(a["kind"] == "preset" and broke_plain is True and not standin)
        self._log(a, plain, harness, trace, broke_plain, standin)
        with self.cond:
            if counted:
                self.counter += 1
            total = self.counter
        yield _line({"type": "scored", "kind": a["kind"], "plain": plain, "harness": harness, "broke_plain": broke_plain,
                     "counted": counted, "failures_collected": total, "unverified": a["kind"] == "free"})

    def _score_side(self, preset: dict | None, output: str) -> dict:
        """Score one answer with the preset's checks; free play has no checks, so nothing is scored."""
        if preset is None:
            return {"output": output, "passed": None, "failed_checks": []}
        result = SCORE({"checks": preset["checks"]}, output)
        labels = {c["id"]: c.get("label", "other") for c in preset["checks"]}
        failed = [{"id": cid, "label": labels.get(cid, "other"), "reason": result.get("details", {}).get(cid, "")}
                  for cid in result.get("failed_checks", [])]
        return {"output": output, "passed": bool(result["passed"]), "failed_checks": failed}

    # -- the log (attendee text: never committed) --------------------------------------------------------------------
    def _log(self, a: dict, plain: dict, harness: dict, trace: dict | None, broke_plain, standin: bool) -> None:
        trace_file = None
        if trace is not None:
            self.trace_dir.mkdir(parents=True, exist_ok=True)
            (self.trace_dir / f"{a['id']}.json").write_text(json.dumps(trace, ensure_ascii=False), encoding="utf-8")
            trace_file = f"arena_traces/{a['id']}.json"
        def side(s: dict) -> dict:
            return {"output": s["output"], "passed": s["passed"],
                    "failed_checks": [f["id"] if isinstance(f, dict) else f for f in s["failed_checks"]]}

        row = {"ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "attempt_id": a["id"], "nickname": a["nickname"], "kind": a["kind"],
               "preset_id": a["preset_id"], "skill_text": a["skill_text"], "input": a["input"], "consent": True,
               "plain": side(plain), "harness": {**side(harness), "trace_file": trace_file},
               "broke_plain": broke_plain, "reviewed": False}
        if standin:
            row["mock"] = True
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        with self.cond, self.log_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    def _rows(self) -> list[dict]:
        if not self.log_path.exists():
            return []
        rows = []
        for line in self.log_path.read_text(encoding="utf-8").splitlines():
            try:
                rows.append(json.loads(line))
            except ValueError:
                continue  # a damaged line is skipped, not fatal
        return rows

    def _count_log_rows(self) -> int:
        return sum(1 for r in self._rows() if r.get("kind") == "preset" and r.get("broke_plain") is True and not r.get("mock"))

    def _highest_logged_id(self) -> int:
        numbers = [int(m.group(1)) for r in self._rows() if (m := re.match(r"a-(\d+)$", str(r.get("attempt_id", ""))))]
        return max(numbers, default=0)

    def stats(self) -> dict:
        rows = self._rows()
        broke = Counter(r["nickname"] for r in rows if r.get("kind") == "preset" and r.get("broke_plain") is True and not r.get("mock"))
        return {"failures_collected": sum(broke.values()), "attempts": len(rows),
                "leaderboard": [{"nickname": n, "broke_plain": c} for n, c in broke.most_common(5)],
                "queue_length": self.queue_length(), "mode": harness_mode(), "provider": provider_label(), "mock": standin_in_use()}


ARENA = Arena()
bp = Blueprint("arena", __name__, url_prefix="/arena")


@bp.get("/presets")
def presets():
    return jsonify([public_preset(p) for p in load_presets()])


@bp.post("/join")
def join():
    payload, status = ARENA.join(request.get_json(silent=True))
    return jsonify(payload), status


@bp.get("/stream/<attempt_id>")
def stream(attempt_id):
    return Response(stream_with_context(ARENA.stream(attempt_id)), mimetype="application/x-ndjson",
                    headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"})


@bp.get("/stats")
def stats():
    return jsonify(ARENA.stats())
