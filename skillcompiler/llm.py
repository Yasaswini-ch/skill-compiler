"""Gemini/Gemma call with exponential backoff and call/latency counters."""
from __future__ import annotations

import os
import re
import threading
import time

from dotenv import load_dotenv

from . import cache, providers

load_dotenv()

_client = None


class Stats:
    """Counters the runner reads to fill trace.json totals.

    Kept per thread, so two runs in different threads (a web server handling two
    requests, or plain and harness side by side) never mix their totals.
    """

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

    def __repr__(self) -> str:
        return "Stats(" + ", ".join(f"{k}={v}" for k, v in self._values().items()) + ")"


stats = Stats()


def _get_client():
    """Create the API client lazily so tests run without a key."""
    global _client
    if _client is None:
        from google import genai

        _client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    return _client


def _generate(prompt: str, model: str) -> str:
    """One raw API request. Tests monkeypatch this."""
    if providers.current() == providers.OPENAI_COMPATIBLE:
        return providers.generate_openai_compatible(prompt, model)
    from google.genai import types

    # Gemma 4 "thinks" by default: ~7000 hidden tokens turned one splitter
    # call into 158 s. MINIMAL cut it to 14 s. Set GEMMA_THINKING=default
    # to use the model's own setting, or another level name to override.
    level = os.environ.get("GEMMA_THINKING", "MINIMAL")
    config = None
    if level.lower() != "default":
        config = types.GenerateContentConfig(
            thinking_config=types.ThinkingConfig(thinking_level=level.upper())
        )
    response = _get_client().models.generate_content(
        model=model, contents=prompt, config=config
    )
    return response.text or ""


class RateLimiter:
    """Sliding-window limiter: at most `rpm` requests in any 60 seconds (all threads).

    The Gemini free tier allows 30 requests per minute per model, and one skill run
    makes roughly 2 calls per step, so long skills hit the limit without this.
    """

    def __init__(self, now=time.monotonic, sleep=time.sleep) -> None:
        self._now, self._sleep = now, sleep
        self._lock = threading.Lock()
        self._times: list[float] = []

    def wait(self, rpm: int) -> None:
        """Block until a request may be sent. rpm <= 0 turns the limiter off."""
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
RETRY_HINT_RE = re.compile(r"retry in (\d+(?:\.\d+)?)s|retryDelay'?\"?:\s*'?\"?(\d+)s", re.IGNORECASE)


def _rpm() -> int:
    """Requests per minute allowed (GEMMA_RPM, default 25; 0 = no limit)."""
    try:
        return int(os.environ.get("GEMMA_RPM", "25"))
    except ValueError:
        return 25


def _retry_delay(exc: Exception, attempt: int) -> float:
    """Seconds to wait after a failed call: the server's own hint on a 429, else backoff."""
    match = RETRY_HINT_RE.search(str(exc))
    hint = float(match.group(1) or match.group(2)) + 1 if match else 0
    return min(max(hint, 2**attempt), 70)


def call_llm(prompt: str, model: str | None = None, retries: int = 3) -> str:
    """Call the model, retrying with backoff on errors (429, 5xx, network)."""
    model = model or os.environ.get("GEMMA_MODEL", "")
    if not model:
        raise RuntimeError("No model set: pass model= or set GEMMA_MODEL in .env")
    if cache.is_enabled():
        cached = cache.get(providers.cache_namespace(model), prompt)
        if cached is not None:
            stats.cache_hits += 1
            return cached
        if cache.is_replay():
            raise cache.CacheMiss(
                "replay mode: this prompt is not in the cache "
                f"(model {model}). Run once with --cache first.")
    last_error: Exception | None = None
    for attempt in range(retries):
        if providers.current() == providers.GEMINI:
            _limiter.wait(_rpm())
        start = time.time()
        try:
            text = _generate(prompt, model)
        except Exception as exc:  # SDK raises several error types
            last_error = exc
            stats.errors += 1
            if attempt < retries - 1:
                time.sleep(_retry_delay(exc, attempt))
            continue
        stats.calls += 1
        stats.latency_ms += int((time.time() - start) * 1000)
        if cache.is_enabled():
            cache.put(providers.cache_namespace(model), prompt, text)
        return text
    raise RuntimeError(f"LLM call failed after {retries} tries: {last_error}")
