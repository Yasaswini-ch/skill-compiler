"""Tests for web/extension.py with a fake event stream: no API key, no network."""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "web"))

import extension  # noqa: E402

SKILL = "---\nname: demo\n---\n1. Say the name.\n2. Say the city.\n"


@pytest.fixture
def client():
    import server
    return server.app.test_client()


def fake_events(lines):
    def events(skill_text, user_input, **kwargs):
        events.kwargs = kwargs
        events.seen = (skill_text, user_input)
        for line in lines:
            yield json.dumps(line) + "\n"
    return events


def test_ping(client):
    data = client.get("/extension/ping").get_json()
    assert data["ok"] is True and data["mode"] == "adaptive"


@pytest.mark.parametrize("body", [None, {}, {"skill_text": "  ", "input": "x"}, {"skill_text": SKILL, "input": ""}, {"skill_text": SKILL, "input": 5}])
def test_bad_bodies_are_400(client, body):
    assert client.post("/extension/run", json=body).status_code == 400


def test_non_json_body_is_400(client):
    assert client.post("/extension/run", data="x", content_type="text/plain").status_code == 400


def test_caps(client):
    long_input = client.post("/extension/run", json={"skill_text": SKILL, "input": "x" * 1501})
    assert long_input.status_code == 400 and "limit is 1500" in long_input.get_json()["error"]
    big_skill = client.post("/extension/run", json={"skill_text": "1. a\n" + "x" * 6000, "input": "x"})
    assert big_skill.status_code == 400 and "limit is 6000" in big_skill.get_json()["error"]
    many = "\n".join(f"{i}. step {i}" for i in range(1, 8))
    steps = client.post("/extension/run", json={"skill_text": many, "input": "x"})
    assert steps.status_code == 400 and "limit is 6" in steps.get_json()["error"]


def test_streams_events_with_the_caps_and_releases_the_lock(client, monkeypatch):
    fake = fake_events([{"type": "run_start"}, {"type": "run_end", "trace": {}}])
    monkeypatch.setattr(extension, "EVENTS", fake)
    reply = client.post("/extension/run", json={"skill_text": SKILL, "input": "hello"})
    assert reply.status_code == 200 and reply.mimetype == "application/x-ndjson"
    assert [json.loads(l)["type"] for l in reply.get_data(as_text=True).splitlines()] == ["run_start", "run_end"]
    assert fake.seen == (SKILL, "hello")
    assert fake.kwargs == {"mode": "adaptive", "max_steps": 6, "timeout_s": 240}
    assert extension.BUSY.acquire(blocking=False)
    extension.BUSY.release()


def test_a_second_run_while_busy_gets_429(client, monkeypatch):
    monkeypatch.setattr(extension, "EVENTS", fake_events([]))
    assert extension.BUSY.acquire(blocking=False)
    try:
        reply = client.post("/extension/run", json={"skill_text": SKILL, "input": "x"})
        assert reply.status_code == 429 and "Try again" in reply.get_json()["error"]
    finally:
        extension.BUSY.release()


def test_a_crash_inside_the_stream_becomes_one_error_line_and_frees_the_lock(client, monkeypatch):
    def boom(skill_text, user_input, **kwargs):
        yield json.dumps({"type": "run_start"}) + "\n"
        raise RuntimeError("kaput")

    monkeypatch.setattr(extension, "EVENTS", boom)
    lines = client.post("/extension/run", json={"skill_text": SKILL, "input": "x"}).get_data(as_text=True).splitlines()
    assert json.loads(lines[-1])["type"] == "error" and "kaput" in json.loads(lines[-1])["message"]
    assert extension.BUSY.acquire(blocking=False)
    extension.BUSY.release()


def test_mode_can_be_set_by_environment(client, monkeypatch):
    monkeypatch.setenv("EXTENSION_MODE", "full")
    assert client.get("/extension/ping").get_json()["mode"] == "full"
