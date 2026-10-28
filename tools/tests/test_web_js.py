"""Runs the Node tests for the web page logic (skipped when Node is not installed)."""
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
NODE = shutil.which("node")
TESTS = sorted((ROOT / "web" / "tests").glob("*.test.js"))


@pytest.mark.skipif(NODE is None, reason="node is not installed")
@pytest.mark.parametrize("path", TESTS, ids=lambda p: p.name)
def test_node_tests_pass(path):
    result = subprocess.run([NODE, "--test", str(path)], cwd=ROOT, capture_output=True, text=True, encoding="utf-8")
    assert result.returncode == 0, result.stdout[-2000:] + result.stderr[-500:]
