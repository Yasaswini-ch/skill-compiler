"""Disk cache of model responses, keyed by a hash of (model, prompt)."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

DEFAULT_DIR = ".skillcompiler_cache"


class CacheMiss(Exception):
    """Raised in replay mode when a response is not in the cache."""


_enabled = False
_replay = False
_dir = Path(DEFAULT_DIR)


def configure(enabled: bool = True, replay: bool = False,
              directory: str | Path = DEFAULT_DIR) -> None:
    """Turn the cache on or off. Replay implies enabled and never calls the API."""
    global _enabled, _replay, _dir
    _enabled = enabled or replay
    _replay = replay
    _dir = Path(directory)


def is_enabled() -> bool:
    return _enabled


def is_replay() -> bool:
    return _replay


def _path(model: str, prompt: str) -> Path:
    key = hashlib.sha256(json.dumps([model, prompt]).encode("utf-8")).hexdigest()
    return _dir / f"{key}.json"


def get(model: str, prompt: str) -> str | None:
    """Cached response, or None."""
    path = _path(model, prompt)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))["text"]
    except (ValueError, KeyError):
        return None  # damaged entry counts as a miss


def put(model: str, prompt: str, text: str) -> None:
    """Store a response."""
    _dir.mkdir(parents=True, exist_ok=True)
    entry = {"model": model, "prompt": prompt, "text": text}
    _path(model, prompt).write_text(json.dumps(entry, ensure_ascii=False), encoding="utf-8")
