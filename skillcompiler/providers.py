"""Model provider switch: Gemini (default) or any OpenAI-compatible server (e.g. Ollama)."""
from __future__ import annotations

import json
import os
import re
import urllib.request

GEMINI = "gemini"
OPENAI_COMPATIBLE = "openai-compatible"
PROVIDERS = (GEMINI, OPENAI_COMPATIBLE)

# Some servers return the model's reasoning inline; it would break format checks.
REASONING_RE = re.compile(r"<(thought|think|thinking)>.*?</\1>", re.DOTALL | re.IGNORECASE)

_provider = GEMINI
_base_url = ""


def configure(provider: str = GEMINI, base_url: str | None = None) -> None:
    """Choose the provider. openai-compatible needs a base URL (or OPENAI_BASE_URL)."""
    global _provider, _base_url
    if provider not in PROVIDERS:
        raise ValueError(f"unknown provider {provider!r}; use one of: {', '.join(PROVIDERS)}")
    _provider = provider
    _base_url = base_url or os.environ.get("OPENAI_BASE_URL", "")
    if provider == OPENAI_COMPATIBLE and not _base_url:
        raise ValueError("--provider openai-compatible needs --base-url "
                         "(for example http://localhost:11434/v1 for Ollama)")


def current() -> str:
    return _provider


def cache_namespace(model: str) -> str:
    """Model name used in cache keys, so providers never share cached answers."""
    return model if _provider == GEMINI else f"{_provider}|{_base_url}|{model}"


def generate_openai_compatible(prompt: str, model: str, timeout: int = 300) -> str:
    """One chat-completions request over plain HTTP. Works with Ollama, vLLM, llama.cpp."""
    body = json.dumps({"model": model,
                       "messages": [{"role": "user", "content": prompt}]}).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    key = os.environ.get("OPENAI_API_KEY")
    if key:  # local servers usually need none
        headers["Authorization"] = f"Bearer {key}"
    request = urllib.request.Request(_base_url.rstrip("/") + "/chat/completions",
                                     data=body, headers=headers, method="POST")
    with urllib.request.urlopen(request, timeout=timeout) as response:
        data = json.load(response)
    text = data["choices"][0]["message"]["content"] or ""
    return REASONING_RE.sub("", text).strip()
