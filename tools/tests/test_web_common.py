"""Runs web/tests/common.test.html in a headless browser (Edge or Chrome) and checks every result.

Skipped when no browser is installed. The page can also be opened by hand to see the same checks.
"""
import html
import json
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

PAGE = Path(__file__).resolve().parents[2] / "web" / "tests" / "common.test.html"
WINDOWS_PATHS = [
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
]


def find_browser():
    for name in ("msedge", "google-chrome", "chromium", "chromium-browser", "chrome"):
        found = shutil.which(name)
        if found:
            return found
    return next((p for p in WINDOWS_PATHS if os.path.exists(p)), None)


@pytest.fixture(scope="module")
def report():
    browser = find_browser()
    if not browser:
        pytest.skip("no Edge/Chrome found")
    with tempfile.TemporaryDirectory() as profile:
        proc = subprocess.run(
            [browser, "--headless", "--disable-gpu", f"--user-data-dir={profile}", "--virtual-time-budget=30000",
             "--dump-dom", PAGE.as_uri()],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=90)
    m = re.search(r'<pre id="result">(.*?)</pre>', proc.stdout, re.S)
    assert m and m.group(1) != "running", "the test page did not finish"
    return json.loads(html.unescape(m.group(1)))


def failures(report, prefix):
    matching = [r for r in report if r["name"].startswith(prefix)]
    assert matching, f"no checks named {prefix!r}"
    return [r for r in matching if not r["ok"]]


def test_fmt_duration_boundaries(report):
    assert not failures(report, "fmtDuration")


def test_main_focus_is_visible_after_skip_link(report):
    assert not failures(report, "skip link") and not failures(report, "main has")


def test_replay_restart_does_not_break_newer_replay(report):
    names = [r["name"] for r in report if r["name"].startswith(("restart", "no spinner", "nothing left", "summary settles", "replay button", "replay skipped"))]
    assert names
    assert not [r for r in report if r["name"] in names and not r["ok"]]
