import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from skillcompiler import __main__ as cli
from skillcompiler import cache, llm, providers
from skillcompiler.plan_io import save_plan

PLAN = {"skill_name": "demo", "source_file": "", "steps": [
    {"id": 1, "title": "Name", "instruction": "Say the name.", "output_format": "text",
     "expected_output": "", "depends_on": []}]}


@pytest.fixture
def server():
    """A tiny fake OpenAI-compatible server (stands in for Ollama)."""
    seen = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            seen.append((self.path, body))
            prompt = body["messages"][0]["content"]
            text = "PASS" if "Does the output follow" in prompt else "Ravi"
            payload = json.dumps({"choices": [{"message": {"content": text}}]}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, *args):
            pass

    httpd = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{httpd.server_port}/v1", seen
    httpd.shutdown()


@pytest.fixture(autouse=True)
def reset():
    yield
    providers.configure(providers.GEMINI)
    cache.configure(enabled=False)


def test_generate_sends_chat_completion(server):
    url, seen = server
    providers.configure(providers.OPENAI_COMPATIBLE, url)
    assert llm.call_llm("hello", model="local-model") == "Ravi"
    path, body = seen[0]
    assert path == "/v1/chat/completions"
    assert body["model"] == "local-model" and body["messages"][0]["content"] == "hello"


def test_cli_run_on_another_model_without_gemini_key(server, monkeypatch, tmp_path, capsys):
    url, seen = server
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    skill = tmp_path / "SKILL.md"
    skill.write_text("1. Say the name.\n", encoding="utf-8")
    plan = tmp_path / "plan.json"
    save_plan(PLAN, plan)
    code = cli.main(["run", str(skill), "--input", "hi", "--plan", str(plan),
                     "--provider", "openai-compatible", "--base-url", url,
                     "--model", "gemma-local"])
    assert code == 0 and capsys.readouterr().out.strip() == "Ravi"
    assert {b["model"] for _, b in seen} == {"gemma-local"} and len(seen) == 2


def test_needs_base_url(monkeypatch):
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
    with pytest.raises(ValueError, match="--base-url"):
        providers.configure(providers.OPENAI_COMPATIBLE)


def test_unknown_provider():
    with pytest.raises(ValueError, match="unknown provider"):
        providers.configure("nope")


def test_providers_do_not_share_cache(monkeypatch, tmp_path, server):
    url, seen = server
    monkeypatch.setattr(llm, "_generate", lambda p, m: "from-gemini")
    cache.configure(enabled=True, directory=tmp_path / "c")
    assert llm.call_llm("same prompt", model="m") == "from-gemini"
    monkeypatch.undo()
    providers.configure(providers.OPENAI_COMPATIBLE, url)
    assert llm.call_llm("same prompt", model="m") == "Ravi"  # not the gemini answer


def test_server_error_retries_then_raises(monkeypatch):
    monkeypatch.setattr(llm.time, "sleep", lambda s: None)
    providers.configure(providers.OPENAI_COMPATIBLE, "http://127.0.0.1:9/v1")  # closed port
    with pytest.raises(RuntimeError, match="failed after 3"):
        llm.call_llm("x", model="m")


@pytest.mark.parametrize("raw,clean", [
    ("<thought>The user wants...\nhmm</thought>hello", "hello"),
    ("<think>x</think>\n\nanswer", "answer"),
    ("plain answer", "plain answer"),
])
def test_reasoning_blocks_are_stripped(raw, clean):
    assert providers.REASONING_RE.sub("", raw).strip() == clean
