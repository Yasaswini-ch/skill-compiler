import pytest


@pytest.fixture(autouse=True)
def no_rate_limit(monkeypatch):
    """Unit tests make many fake calls; do not throttle them."""
    monkeypatch.setenv("GEMMA_RPM", "0")
