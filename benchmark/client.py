"""Benchmark's own copy of the Gemma client (contract 2.3).

It mirrors skillcompiler/llm.py on purpose, so plain and harness runs are comparable:
  - same model (GEMMA_MODEL),
  - same thinking setting (GEMMA_THINKING, default MINIMAL; "default" = the model's own setting),
  - same pacing (GEMMA_RPM requests per minute, default 25; 0 = off),
  - on a 429 it waits for the server's "retry in Ns" hint, else backs off 1, 2, 4 ... seconds.

Extras: call/latency counters (`stats`), and an optional disk cache (`configure_cache(True)`) kept
in benchmark/.cache/. The cache key includes the thinking level, which skillcompiler's cache does not.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import threading
import time
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

CACHE_DIR = Path(__file__).resolve().parent / ".cache"
RETRY_HINT_RE = re.compile(r"retry in (\d+(?:\.\d+)?)s|retryDelay'?\"?:\s*'?\"?(\d+)s", re.IGNORECASE)

_client = None
_cache_on = False


class Stats:
    """Counters for the current thread: calls, latency_ms, errors, cache_hits."""

    FIELDS = ("calls", "latency_ms", "errors", "cache_hits")

    def __init__(self) -> None:
        object.__setattr__(self, "_local", threading.local())

    def _values(self) -> dict:
        local = object.__getattribute__(self, "_local")
        if not hasattr(local, "values"):
            local.values = dict.fromkeys(self.FIELDS, 0)
        return local.values

    def __getattr__(self, name: str) -> int:
        if name in self.FIELDS:
            return self._values()[name]
        raise AttributeError(name)

    def __setattr__(self, name: str, value: int) -> None:
        if name not in self.FIELDS:
            raise AttributeError(name)
        self._values()[name] = value

    def reset(self) -> None:
        self._values().update(dict.fromkeys(self.FIELDS, 0))


stats = Stats()


class RateLimiter:
    """Sliding window: at most `rpm` requests in any 60 seconds."""

    def __init__(self, now=time.monotonic, sleep=time.sleep) -> None:
        self._now, self._sleep = now, sleep
        self._lock = threading.Lock()
        self._times: list[float] = []

    def wait(self, rpm: int) -> None:
        if rpm <= 0:
            return
        while True:
            with self._lock:
                now = self._now()
                self._times = [t for t in self._times if now - t < 60]
                if len(self._times) < rpm:
                    self._times.append(now)
                    return
                delay = 60 - (now - self._times[0])
            self._sleep(max(delay, 0.05))


_limiter = RateLimiter()


def rpm() -> int:
    """Requests per minute allowed (GEMMA_RPM, default 25; 0 = no limit)."""
    try:
        return int(os.environ.get("GEMMA_RPM", "25"))
    except ValueError:
        return 25


def thinking_level() -> str:
    """The GEMMA_THINKING value in effect, as recorded in results.json."""
    return os.environ.get("GEMMA_THINKING", "MINIMAL")


def current_model() -> str:
    return os.environ.get("GEMMA_MODEL", "")


def settings() -> dict:
    """Run settings worth recording next to the numbers."""
    return {"model": current_model(), "gemma_thinking": thinking_level(), "gemma_rpm": rpm()}


def configure_cache(enabled: bool) -> None:
    global _cache_on
    _cache_on = enabled


def _cache_path(model: str, prompt: str) -> Path:
    key = json.dumps([model, thinking_level().upper(), prompt], ensure_ascii=False)
    return CACHE_DIR / (hashlib.sha256(key.encode("utf-8")).hexdigest() + ".json")


def _get_client():
    """Create the API client lazily so importing this module needs no key."""
    global _client
    if _client is None:
        from google import genai

        _client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    return _client


def _generate(prompt: str, model: str) -> str:
    """One raw API request. Tests monkeypatch this."""
    from google.genai import types

    level = thinking_level()
    config = None
    if level.lower() != "default":
        config = types.GenerateContentConfig(
            thinking_config=types.ThinkingConfig(thinking_level=level.upper())
        )
    response = _get_client().models.generate_content(model=model, contents=prompt, config=config)
    return response.text or ""


def retry_delay(exc: Exception, attempt: int) -> float:
    """Seconds to wait after a failed call: the server's hint on a 429 (cap 70 s), else backoff."""
    match = RETRY_HINT_RE.search(str(exc))
    hint = float(match.group(1) or match.group(2)) + 1 if match else 0
    return min(max(hint, 2**attempt), 70)


def call_llm(prompt: str, model: str | None = None, retries: int = 3) -> str:
    """Call the model, pacing requests and retrying on errors (429, 5xx, network)."""
    model = model or current_model()
    if not model:
        raise RuntimeError("No model set: pass model= or set GEMMA_MODEL in .env")
    path = _cache_path(model, prompt)
    if _cache_on and path.exists():
        stats.cache_hits += 1
        return json.loads(path.read_text(encoding="utf-8"))["text"]
    last_error: Exception | None = None
    for attempt in range(retries):
        _limiter.wait(rpm())
        start = time.time()
        try:
            text = _generate(prompt, model)
        except Exception as exc:  # the SDK raises several error types
            last_error = exc
            stats.errors += 1
            if attempt < retries - 1:
                time.sleep(retry_delay(exc, attempt))
            continue
        stats.calls += 1
        stats.latency_ms += int((time.time() - start) * 1000)
        if _cache_on:
            CACHE_DIR.mkdir(exist_ok=True)
            path.write_text(json.dumps({"model": model, "text": text}), encoding="utf-8")
        return text
    raise RuntimeError(f"LLM call failed after {retries} tries: {last_error}")
