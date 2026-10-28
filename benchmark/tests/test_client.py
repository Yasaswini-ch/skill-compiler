"""Tests for benchmark/client.py with the API call faked."""
import pytest

from benchmark import client


@pytest.fixture(autouse=True)
def _env(monkeypatch, tmp_path):
    monkeypatch.setenv("GEMMA_MODEL", "m1")
    monkeypatch.setenv("GEMMA_RPM", "0")
    monkeypatch.setattr(client, "CACHE_DIR", tmp_path / "cache")
    monkeypatch.setattr(client.time, "sleep", lambda s: None)
    client.configure_cache(False)
    client.stats.reset()
    yield
    client.configure_cache(False)


def test_retry_delay_uses_server_hint_and_caps():
    assert client.retry_delay(Exception("429 ... retry in 48s"), 0) == 49
    assert client.retry_delay(Exception("retry in 500s"), 0) == 70
    assert client.retry_delay(Exception("boom"), 2) == 4


def test_retries_then_succeeds(monkeypatch):
    calls = []

    def fake(prompt, model):
        calls.append(model)
        if len(calls) < 3:
            raise RuntimeError("429 RESOURCE_EXHAUSTED retry in 1s")
        return "ok"

    monkeypatch.setattr(client, "_generate", fake)
    assert client.call_llm("hi") == "ok"
    assert calls == ["m1"] * 3
    assert client.stats.calls == 1 and client.stats.errors == 2


def test_gives_up_after_retries(monkeypatch):
    monkeypatch.setattr(client, "_generate", lambda p, m: (_ for _ in ()).throw(RuntimeError("down")))
    with pytest.raises(RuntimeError, match="failed after 3 tries"):
        client.call_llm("hi")


def test_missing_model_raises(monkeypatch):
    monkeypatch.delenv("GEMMA_MODEL")
    with pytest.raises(RuntimeError, match="No model set"):
        client.call_llm("hi")


def test_cache_hit_makes_no_call_and_key_depends_on_thinking(monkeypatch):
    n = []
    monkeypatch.setattr(client, "_generate", lambda p, m: n.append(1) or "answer")
    client.configure_cache(True)
    assert client.call_llm("q") == "answer"
    assert client.call_llm("q") == "answer"
    assert len(n) == 1 and client.stats.cache_hits == 1
    monkeypatch.setenv("GEMMA_THINKING", "default")
    client.call_llm("q")
    assert len(n) == 2


def test_settings_record_thinking(monkeypatch):
    monkeypatch.delenv("GEMMA_THINKING", raising=False)
    assert client.settings() == {"model": "m1", "gemma_thinking": "MINIMAL", "gemma_rpm": 0}
    monkeypatch.setenv("GEMMA_THINKING", "default")
    assert client.settings()["gemma_thinking"] == "default"


def test_rate_limiter_waits_when_window_is_full():
    t = [0.0]
    slept = []
    lim = client.RateLimiter(now=lambda: t[0], sleep=lambda s: (slept.append(s), t.__setitem__(0, t[0] + s)))
    for _ in range(2):
        lim.wait(2)
    lim.wait(2)  # third request must wait for the first to leave the 60 s window
    assert slept and sum(slept) >= 59.9
