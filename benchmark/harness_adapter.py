"""Connects the benchmark to A's harness.

    from benchmark.harness_adapter import run_skill, HARNESS_IS_MOCK, IMPORT_ERROR

If `from skillcompiler import run_skill` works, the REAL harness is used and HARNESS_IS_MOCK is False.
Only if the import fails is a stand-in used: it runs plain Gemma, relabels the trace as mode "harness"
with "mock": true, and HARNESS_IS_MOCK is True. Mock numbers must never be shown as results.
"""
from __future__ import annotations

import os

from benchmark.run_plain import run_plain

IMPORT_ERROR: str | None = None
try:
    from skillcompiler import run_skill  # A's harness
    HARNESS_IS_MOCK = False
except ImportError as exc:  # harness not merged yet, or a dependency is missing
    HARNESS_IS_MOCK = True
    IMPORT_ERROR = repr(exc)

    def run_skill(skill_text: str, user_input: str, model: str | None = None) -> dict:  # noqa: F811
        """STAND-IN, not the real harness: one plain call labelled as a mock harness trace."""
        trace = run_plain(skill_text, user_input, model)
        trace["mode"] = "harness"
        trace["mock"] = True
        return trace


def verifier_setting() -> str:
    """"off" if SKILLCOMPILER_VERIFY=0 (the harness's own rule), else "on"."""
    return "off" if os.environ.get("SKILLCOMPILER_VERIFY", "1") == "0" else "on"


def configure_harness_cache(enabled: bool, directory: str) -> None:
    """Turn on A's response cache (debugging only). No-op for the stand-in."""
    if enabled and not HARNESS_IS_MOCK:
        from skillcompiler import cache
        cache.configure(True, directory=directory)
