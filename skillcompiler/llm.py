"""Gemini/Gemma call with exponential backoff and call/latency counters."""
from __future__ import annotations

import os
import time
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()

_client = None


@dataclass
class Stats:
    """Counters the runner reads to fill trace.json totals."""

    calls: int = 0
    latency_ms: int = 0
    errors: int = 0

    def reset(self) -> None:
        self.calls = 0
        self.latency_ms = 0
        self.errors = 0


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


def call_llm(prompt: str, model: str | None = None, retries: int = 3) -> str:
    """Call the model, retrying with backoff on errors (429, 5xx, network)."""
    model = model or os.environ.get("GEMMA_MODEL", "")
    if not model:
        raise RuntimeError("No model set: pass model= or set GEMMA_MODEL in .env")
    last_error: Exception | None = None
    for attempt in range(retries):
        start = time.time()
        try:
            text = _generate(prompt, model)
        except Exception as exc:  # SDK raises several error types
            last_error = exc
            stats.errors += 1
            if attempt < retries - 1:
                time.sleep(2**attempt)
            continue
        stats.calls += 1
        stats.latency_ms += int((time.time() - start) * 1000)
        return text
    raise RuntimeError(f"LLM call failed after {retries} tries: {last_error}")
