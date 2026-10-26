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


class BrowserLaunchError(Exception):
    """The browser could not start or produced no page at all (environment problem, not a test failure)."""


def browser_args(browser, profile, is_root):
    args = [browser, "--headless", "--disable-gpu", f"--user-data-dir={profile}", "--virtual-time-budget=30000"]
    if is_root:
        args.append("--no-sandbox")   # Chromium refuses to start as root (Docker, CI) without it
    return args + ["--dump-dom", PAGE.as_uri()]


def parse_report(stdout, stderr=""):
    """Return the list of check results from the dumped page.

    No page at all means the browser did not launch (BrowserLaunchError). A page whose tests never
    finished is a real failure and raises AssertionError.
    """
    if "<html" not in stdout:
        raise BrowserLaunchError((stderr or "no output").strip()[-300:])
    m = re.search(r'<pre id="result">(.*?)</pre>', stdout, re.S)
    assert m and m.group(1) != "running", "the test page loaded but did not finish its checks"
    return json.loads(html.unescape(m.group(1)))


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
    is_root = hasattr(os, "geteuid") and os.geteuid() == 0
    with tempfile.TemporaryDirectory() as profile:
        try:
            proc = subprocess.run(browser_args(browser, profile, is_root), capture_output=True, text=True,
                                  encoding="utf-8", errors="replace", timeout=90)
        except OSError as e:
            pytest.skip(f"browser could not be started: {e}")
    try:
        return parse_report(proc.stdout, proc.stderr)
    except BrowserLaunchError as e:
        pytest.skip(f"browser started but produced no page (exit {proc.returncode}): {e}")


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


# --- the launcher helpers themselves (no browser needed) ---

def test_no_sandbox_only_when_running_as_root():
    assert "--no-sandbox" in browser_args("chrome", "p", is_root=True)
    assert "--no-sandbox" not in browser_args("chrome", "p", is_root=False)


def test_browser_args_always_dump_the_test_page():
    args = browser_args("chrome", "p", is_root=False)
    assert args[-2:] == ["--dump-dom", PAGE.as_uri()] and args[0] == "chrome"


def test_no_page_output_means_launch_failure_not_a_test_failure():
    with pytest.raises(BrowserLaunchError):
        parse_report("", "Running as root without --no-sandbox is not supported")


def test_page_that_never_finishes_is_a_real_failure():
    with pytest.raises(AssertionError):
        parse_report('<html><pre id="result">running</pre></html>')
    with pytest.raises(AssertionError):
        parse_report("<html><body>no result element</body></html>")


def test_finished_page_returns_its_results():
    out = '<html><pre id="result">[{"name":"a","ok":false,"detail":"x &amp; y"}]</pre></html>'
    assert parse_report(out) == [{"name": "a", "ok": False, "detail": "x & y"}]
