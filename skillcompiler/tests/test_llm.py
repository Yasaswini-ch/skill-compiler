import pytest

from skillcompiler import llm


def test_retries_then_succeeds(monkeypatch):
    llm.stats.reset()
    monkeypatch.setattr(llm.time, "sleep", lambda s: None)
    answers = iter([RuntimeError("429"), RuntimeError("500"), "ok"])

    def fake(prompt, model):
        a = next(answers)
        if isinstance(a, Exception):
            raise a
        return a

    monkeypatch.setattr(llm, "_generate", fake)
    assert llm.call_llm("hi", model="m") == "ok"
    assert llm.stats.calls == 1 and llm.stats.errors == 2


def test_gives_up_after_retries(monkeypatch):
    llm.stats.reset()
    monkeypatch.setattr(llm.time, "sleep", lambda s: None)

    def boom(prompt, model):
        raise RuntimeError("429")

    monkeypatch.setattr(llm, "_generate", boom)
    with pytest.raises(RuntimeError, match="failed after 3"):
        llm.call_llm("hi", model="m")
