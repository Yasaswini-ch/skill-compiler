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
    client.configure_provider(client.GEMINI)
    client.stats.reset()
    yield
    client.configure_cache(False)
    client.configure_provider(client.GEMINI)


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
    assert client.settings() == {"model": "m1", "provider": "gemini", "base_url": None,
                                 "gemma_thinking": "MINIMAL", "gemma_rpm": 0}
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


# --- openai-compatible provider (a local model server such as Ollama) -------------------------------------------

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer


@pytest.fixture
def fake_server():
    """A tiny chat-completions server. server.requests records (path, body); server.reply is the answer text."""
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            self.server.requests.append((self.path, body, self.headers.get("Authorization")))
            payload = json.dumps({"choices": [{"message": {"content": self.server.reply}}]}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, *args):
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    server.requests, server.reply = [], "hello"
    threading.Thread(target=server.serve_forever, daemon=True).start()
    server.url = f"http://127.0.0.1:{server.server_port}/v1"
    yield server
    server.shutdown()


def test_local_provider_sends_a_chat_request_and_strips_reasoning(fake_server, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    fake_server.reply = "<think>let me see</think>\nbilling "
    client.configure_provider(client.OPENAI_COMPATIBLE, fake_server.url)
    assert client.call_llm("my prompt", "gemma-local") == "billing"
    path, body, auth = fake_server.requests[0]
    assert path == "/v1/chat/completions" and auth is None
    assert body == {"model": "gemma-local", "messages": [{"role": "user", "content": "my prompt"}]}
    assert client.stats.calls == 1


def test_local_provider_skips_gemini_pacing_and_reports_no_thinking(fake_server, monkeypatch):
    monkeypatch.setenv("GEMMA_RPM", "1")
    monkeypatch.setattr(client._limiter, "wait", lambda rpm: pytest.fail("the Gemini limiter was used for a local model"))
    client.configure_provider(client.OPENAI_COMPATIBLE, fake_server.url)
    client.call_llm("a")
    client.call_llm("b")
    s = client.settings()
    assert s["provider"] == "openai-compatible" and s["base_url"] == fake_server.url
    assert s["gemma_thinking"].startswith("n/a") and s["gemma_rpm"] is None


def test_local_provider_needs_a_base_url_and_rejects_unknown_names(monkeypatch):
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
    with pytest.raises(ValueError, match="base URL"):
        client.configure_provider(client.OPENAI_COMPATIBLE)
    with pytest.raises(ValueError, match="unknown provider"):
        client.configure_provider("nope")
    assert client.provider() == "gemini"  # a failed call changes nothing


def test_cache_key_differs_between_providers(fake_server, monkeypatch):
    client.configure_cache(True)
    real_generate = client._generate
    monkeypatch.setattr(client, "_generate", lambda p, m: "from-gemini")
    assert client.call_llm("q") == "from-gemini"
    client.configure_provider(client.OPENAI_COMPATIBLE, fake_server.url)
    monkeypatch.setattr(client, "_generate", real_generate)
    fake_server.reply = "from-local"
    assert client.call_llm("q") == "from-local"  # not the cached Gemini answer
