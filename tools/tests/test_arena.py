"""Tests for web/arena.py with fake model adapters: no API key, no network."""
import json
import sys
import threading
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "web"))

import arena  # noqa: E402

PRESET = {"id": "p01", "title": "The invoice", "tag": "reliable", "why_it_breaks": "arithmetic", "steps": 3,
          "skill_text": "---\nname: inv\n---\n1. Add.\n2. Tax.\n3. Output JSON.", "input": "10 and 20",
          "checks": [{"id": "c1", "type": "contains", "value": "OK", "label": "wrong_format"},
                     {"id": "c2", "type": "contains", "value": "TOTAL", "label": "lost_track"}],
          "tested": {"model": "m", "date": "2026-10-30", "plain_runs": 5, "plain_failed": 4, "harness_runs": 3, "harness_failed": 0}}
SKILL3 = "---\nname: s\n---\n1. One.\n2. Two.\n3. Three."
GOOD = {"consent": True, "nickname": "guest-7", "kind": "preset", "preset_id": "p01", "input": "10 and 20"}


def fake_score(task, output):
    failed = [c["id"] for c in task["checks"] if c["value"] not in output]
    return {"passed": not failed, "failed_checks": failed, "failure_label": None,
            "details": {cid: f"missing {cid}" for cid in failed}}


def make_events(final_output="OK TOTAL", delay=0.0, error=None, gate=None):
    def events(skill_text, user_input, **kwargs):
        events.calls.append(kwargs)
        yield json.dumps({"type": "run_start", "will_split": True, "mode": kwargs.get("mode")}) + "\n"
        yield json.dumps({"type": "plan", "skill": "s", "steps": [{"id": 1, "title": "A", "instruction": "do"}]}) + "\n"
        if gate:
            gate.wait(5)
        if delay:
            time.sleep(delay)
        if error:
            yield json.dumps({"type": "error", "message": error}) + "\n"
            return
        trace = {"skill": "s", "mode": "harness", "mock": False, "steps": [], "final_output": final_output, "totals": {"llm_calls": 3}}
        yield json.dumps({"type": "run_end", "trace": trace}) + "\n"
    events.calls = []
    return events


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(arena, "ARENA", arena.Arena(tmp_path / "log.jsonl", tmp_path / "traces"))
    monkeypatch.setattr(arena, "load_presets", lambda: [PRESET])
    monkeypatch.setattr(arena, "SCORE", fake_score)
    monkeypatch.setattr(arena, "PLAIN", lambda skill, text, model=None: {"final_output": "nope"})
    monkeypatch.setattr(arena, "EVENTS", make_events())
    monkeypatch.delenv("ARENA_PROVIDER", raising=False)
    monkeypatch.delenv("ARENA_MODE", raising=False)
    return arena.ARENA


def events_of(gen):
    return [json.loads(line) for line in gen]


def run_attempt(env, **override):
    body, status = env.join({**GOOD, **override})
    assert status == 200, body
    return events_of(env.stream(body["attempt_id"]))


def rows(env):
    return [json.loads(l) for l in env.log_path.read_text(encoding="utf-8").splitlines()]


# ------------------------------------------------------------------ limits and validation

@pytest.mark.parametrize("override,fragment", [
    ({"consent": False}, "tick the box"),
    ({"consent": "yes"}, "tick the box"),
    ({"nickname": ""}, "Nickname"),
    ({"nickname": "x" * 21}, "Nickname"),
    ({"nickname": "<script>"}, "Nickname"),
    ({"kind": "other"}, "kind"),
    ({"input": "   "}, "empty"),
    ({"input": "x" * (arena.MAX_INPUT + 1)}, "limit is 1500"),
    ({"preset_id": "nope"}, "Unknown challenge"),
])
def test_join_rejects_bad_requests(env, override, fragment):
    body, status = env.join({**GOOD, **override})
    assert status == 400 and fragment in body["error"]


def test_join_rejects_non_objects(env):
    assert env.join("text")[1] == 400 and env.join(None)[1] == 400


def test_free_play_limits(env):
    free = {**GOOD, "kind": "free", "skill_text": SKILL3}
    assert env.join(free)[1] == 200
    assert env.join({**free, "skill_text": ""})[1] == 400
    assert env.join({**free, "skill_text": "x" * (arena.MAX_SKILL + 1)})[1] == 400
    seven = "---\nname: s\n---\n" + "\n".join(f"{i}. Step." for i in range(1, 8))
    body, status = env.join({**free, "skill_text": seven})
    assert status == 400 and "7 steps; the limit is 6" in body["error"]


def test_five_attempts_per_nickname(env):
    for _ in range(arena.MAX_ATTEMPTS_PER_NICKNAME):
        assert env.join(GOOD)[1] == 200
    body, status = env.join(GOOD)
    assert status == 400 and "5 attempts" in body["error"]
    assert env.join({**GOOD, "nickname": "someone-else"})[1] == 200


def test_the_response_says_which_mode_runs(env, monkeypatch):
    monkeypatch.setenv("ARENA_MODE", "full")
    body, _ = env.join(GOOD)
    assert body["mode"] == "full" and body["provider"] == "Gemini API" and body["position"] == 1


# ------------------------------------------------------------------ scoring and the counter

def test_challenge_where_plain_fails_counts(env):
    evs = run_attempt(env)
    kinds = [e["type"] for e in evs]
    assert kinds[0] == "start" and kinds[1] == "plain" and kinds[-1] == "scored" and "run_end" in kinds
    plain = evs[1]["result"]
    assert plain["passed"] is False and [f["id"] for f in plain["failed_checks"]] == ["c1", "c2"]
    assert plain["failed_checks"][0]["label"] == "wrong_format"
    scored = evs[-1]
    assert scored["broke_plain"] is True and scored["counted"] is True and scored["failures_collected"] == 1
    assert scored["harness"]["passed"] is True and scored["unverified"] is False
    assert env.stats()["failures_collected"] == 1


def test_if_plain_passes_nothing_is_counted(env, monkeypatch):
    monkeypatch.setattr(arena, "PLAIN", lambda s, t, model=None: {"final_output": "OK TOTAL"})
    scored = run_attempt(env)[-1]
    assert scored["broke_plain"] is False and scored["counted"] is False and scored["failures_collected"] == 0


def test_free_play_is_unverified_and_never_counted(env):
    scored = run_attempt(env, kind="free", skill_text=SKILL3, preset_id=None)[-1]
    assert scored["unverified"] is True and scored["broke_plain"] is None and scored["counted"] is False
    assert scored["plain"]["passed"] is None and scored["harness"]["passed"] is None
    row = rows(env)[0]
    assert row["kind"] == "free" and row["broke_plain"] is None and row["plain"]["passed"] is None and row["preset_id"] is None
    assert env.stats()["failures_collected"] == 0


def test_a_plain_api_error_is_not_a_model_failure(env, monkeypatch):
    def boom(skill, text, model=None):
        raise RuntimeError("503")
    monkeypatch.setattr(arena, "PLAIN", boom)
    evs = run_attempt(env)
    plain, scored = evs[1]["result"], evs[-1]
    assert plain["passed"] is None and "503" in plain["error"]
    assert scored["broke_plain"] is None and scored["counted"] is False
    assert any(e["type"] == "run_end" for e in evs)               # the harness still ran


def test_a_harness_error_is_shown_and_the_run_ends_cleanly(env, monkeypatch):
    monkeypatch.setattr(arena, "EVENTS", make_events(error="The model API failed 3 calls in a row"))
    evs = run_attempt(env)
    assert any(e["type"] == "error" for e in evs)
    scored = evs[-1]
    assert scored["harness"]["passed"] is None and "3 calls" in scored["harness"]["error"]
    assert scored["broke_plain"] is True and scored["counted"] is True   # plain failed a scored challenge regardless


def test_stand_in_results_are_marked_mock_and_not_counted(env, monkeypatch):
    monkeypatch.setattr(arena, "standin_in_use", lambda: True)
    evs = run_attempt(env)
    assert evs[0]["mock"] is True and evs[-1]["counted"] is False
    assert rows(env)[0]["mock"] is True and env.stats()["failures_collected"] == 0


def test_a_mock_challenge_is_never_counted(env, monkeypatch):
    monkeypatch.setattr(arena, "load_presets", lambda: [{**PRESET, "mock": True}])
    evs = run_attempt(env)
    assert evs[0]["mock"] is True and evs[-1]["broke_plain"] is True and evs[-1]["counted"] is False
    assert rows(env)[0]["mock"] is True and env.stats()["failures_collected"] == 0


def test_the_arena_passes_its_mode_and_limits_to_the_harness(env, monkeypatch):
    monkeypatch.setenv("ARENA_MODE", "full")
    ev = make_events()
    monkeypatch.setattr(arena, "EVENTS", ev)
    run_attempt(env)
    assert ev.calls[0]["mode"] == "full" and ev.calls[0]["max_steps"] == 6 and ev.calls[0]["timeout_s"] == arena.RUN_TIMEOUT_S


def test_leaderboard(env):
    for nick in ("ann", "ann", "bob"):
        run_attempt(env, nickname=nick)
    board = env.stats()["leaderboard"]
    assert board[0] == {"nickname": "ann", "broke_plain": 2} and board[1]["nickname"] == "bob"


# ------------------------------------------------------------------ the log: contract shape and privacy

def test_log_rows_match_the_phase2_contract_and_hold_no_personal_data(env):
    run_attempt(env)
    row = rows(env)[0]
    schema = json.loads((ROOT / "contract" / "phase2" / "arena_log_line.schema.json").read_text(encoding="utf-8"))
    jsonschema = pytest.importorskip("jsonschema")
    jsonschema.validate(row, schema)
    assert set(row) == {"ts", "attempt_id", "nickname", "kind", "preset_id", "skill_text", "input", "consent",
                        "plain", "harness", "broke_plain", "reviewed"}                   # no ip, no name, no email
    assert row["consent"] is True and row["reviewed"] is False and row["attempt_id"] == "a-0001"
    assert row["harness"]["trace_file"] == "arena_traces/a-0001.json"
    assert (env.trace_dir / "a-0001.json").exists()


def test_attempt_ids_continue_after_a_restart(env, tmp_path):
    run_attempt(env)
    run_attempt(env)
    fresh = arena.Arena(env.log_path, env.trace_dir)
    body, _ = fresh.join(GOOD)
    assert body["attempt_id"] == "a-0003"


def test_a_damaged_log_line_does_not_break_the_stats(env):
    run_attempt(env)
    with env.log_path.open("a", encoding="utf-8") as f:
        f.write("{not json\n")
    assert env.stats()["attempts"] == 1


# ------------------------------------------------------------------ the queue

def test_one_run_at_a_time_in_join_order(env, monkeypatch):
    gate = threading.Event()
    order = []
    ev = make_events(gate=gate)

    def tracked(skill, text, **kw):
        order.append(text)
        yield from ev(skill, text, **kw)

    monkeypatch.setattr(arena, "EVENTS", tracked)
    first, _ = env.join({**GOOD, "input": "first"})
    second, _ = env.join({**GOOD, "input": "second", "nickname": "other"})
    assert (first["position"], second["position"]) == (1, 2)
    results = {}

    def go(name, body):
        results[name] = events_of(env.stream(body["attempt_id"]))

    t1 = threading.Thread(target=go, args=("first", first))
    t2 = threading.Thread(target=go, args=("second", second))
    t1.start()
    time.sleep(0.3)
    t2.start()
    time.sleep(1.3)
    assert order == ["first"]                                    # the second waits while the first runs
    gate.set()
    t1.join(10)
    t2.join(10)
    assert order == ["first", "second"]
    waiting = [e for e in results["second"] if e["type"] == "queue"]
    assert waiting and waiting[0]["position"] == 2 and waiting[0]["estimated_wait_s"] > 0   # it was told to wait
    assert results["second"][-1]["type"] == "scored" and results["first"][-1]["type"] == "scored"


def test_a_page_that_disconnects_while_waiting_is_dropped(env, monkeypatch):
    gate = threading.Event()
    monkeypatch.setattr(arena, "EVENTS", make_events(gate=gate))
    a, _ = env.join({**GOOD, "input": "a"})
    b, _ = env.join({**GOOD, "input": "b", "nickname": "b"})
    c, _ = env.join({**GOOD, "input": "c", "nickname": "c"})
    runner_a = threading.Thread(target=lambda: events_of(env.stream(a["attempt_id"])))
    runner_a.start()
    time.sleep(0.3)
    stream_b = env.stream(b["attempt_id"])
    assert json.loads(next(stream_b))["type"] == "queue"
    stream_b.close()                                             # b's tab closed while waiting
    assert b["attempt_id"] not in env.order and env.attempts[b["attempt_id"]]["status"] == "dropped"
    gate.set()
    runner_a.join(10)
    assert events_of(env.stream(c["attempt_id"]))[-1]["type"] == "scored"   # c is not stuck behind b


def test_closing_the_page_mid_run_frees_the_slot(env, monkeypatch):
    monkeypatch.setattr(arena, "EVENTS", make_events(delay=0.05))
    a, _ = env.join(GOOD)
    stream = env.stream(a["attempt_id"])
    next(stream)
    next(stream)
    stream.close()
    assert env.running is None and a["attempt_id"] not in env.order and env.attempts[a["attempt_id"]]["status"] == "dropped"
    assert not env.log_path.exists()                             # an unfinished attempt is not logged or counted


def test_an_attempt_that_never_connects_is_dropped(env):
    clock = {"t": 0.0}
    env.clock = lambda: clock["t"]
    a, _ = env.join(GOOD)
    clock["t"] = arena.CONNECT_TTL_S + 1
    assert env.queue_length() == 0 and env.attempts[a["attempt_id"]]["status"] == "dropped"
    assert "dropped" in events_of(env.stream(a["attempt_id"]))[0]["message"]


def test_an_attempt_cannot_be_run_twice(env):
    a, _ = env.join(GOOD)
    events_of(env.stream(a["attempt_id"]))
    assert events_of(env.stream(a["attempt_id"]))[0]["type"] == "error"
    assert events_of(env.stream("a-9999"))[0]["message"] == "Unknown attempt."


# ------------------------------------------------------------------ settings, HTTP, privacy of files

def test_local_provider_label_and_plain_path(env, monkeypatch):
    monkeypatch.setenv("ARENA_PROVIDER", "local")
    monkeypatch.setenv("ARENA_MODEL", "gemma4:e2b")
    assert arena.provider_label() == "LOCAL MODEL (gemma4:e2b)"
    assert env.stats()["provider"] == "LOCAL MODEL (gemma4:e2b)"


def test_http_routes_and_private_files_are_not_served(env):
    import server
    client = server.app.test_client()
    presets = client.get("/arena/presets").get_json()
    assert presets[0]["id"] == "p01" and "checks" not in presets[0] and presets[0]["n_checks"] == 2
    assert client.post("/arena/join", json={**GOOD, "consent": False}).status_code == 400
    ok = client.post("/arena/join", json=GOOD)
    assert ok.status_code == 200 and ok.get_json()["attempt_id"] == "a-0001"
    assert client.get("/arena/stats").get_json()["queue_length"] == 1
    for private in ("arena_log.jsonl", "arena_traces/a-0001.json", "arena.py", "server.py", "__pycache__/x.pyc"):
        assert client.get("/" + private).status_code == 404, private
    assert client.get("/index.html").status_code == 200


def test_attendee_files_are_gitignored():
    text = (ROOT / ".gitignore").read_text(encoding="utf-8")
    assert "web/arena_log.jsonl" in text and "web/arena_traces/" in text
