"""Save and load plans as JSON or YAML, so a skill is compiled once and run many times."""
from __future__ import annotations

import json
from pathlib import Path

import yaml

from .splitter import validate_steps

YAML_SUFFIXES = {".yaml", ".yml"}


def save_plan(plan: dict, path: str | Path) -> None:
    """Write a plan; the format follows the extension (.json, .yaml, .yml)."""
    path = Path(path)
    if path.suffix.lower() in YAML_SUFFIXES:
        text = yaml.safe_dump(plan, sort_keys=False, allow_unicode=True)
    else:
        text = json.dumps(plan, indent=2, ensure_ascii=False) + "\n"
    path.write_text(text, encoding="utf-8")


def load_plan(path: str | Path) -> dict:
    """Read and validate a plan. Raises ValueError if it is not a usable plan."""
    path = Path(path)
    text = path.read_text(encoding="utf-8")
    try:
        data = yaml.safe_load(text) if path.suffix.lower() in YAML_SUFFIXES else json.loads(text)
    except (ValueError, yaml.YAMLError) as exc:
        raise ValueError(f"{path} is not valid {path.suffix or 'plan'} data: {exc}") from exc
    if not isinstance(data, dict) or "steps" not in data:
        raise ValueError(f"{path} is not a plan: it needs a top-level 'steps' list")
    data["steps"] = validate_steps(data["steps"])
    data.setdefault("skill_name", "skill")
    data.setdefault("source_file", "")
    return data
