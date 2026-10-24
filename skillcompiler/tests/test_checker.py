import pytest

from skillcompiler import checker, llm


@pytest.mark.parametrize("fmt,output,ok", [
    ("text", "Ravi", True),
    ("text", "   ", False),
    ("json", '{"a": 1}', True),
    ("json", '```json\n{"a": 1}\n```', True),
    ("json", "{a: 1}", False),
    ("list", "- a\n- b", True),
    ("list", "1. a", True),
    ("list", '["a", "b"]', True),
    ("list", "just one line", False),
    ("number", "42", True),
    ("number", "3.5.", True),
    ("number", "about 4", False),
    ("one_of:billing|technical|account", "billing", True),
    ("one_of:billing|technical|account", "  Billing. ", True),
    ("one_of:billing|technical|account", "It looks like a billing issue", False),
    ("max_words:5", "one two three", True),
    ("max_words:3", "one two three four", False),
    ("weird", "anything", True),
])
def test_check_format(fmt, output, ok):
    assert checker.check_format(fmt, output)[0] is ok


def test_format_note_is_actionable():
    ok, note = checker.check_format("max_words:3", "a b c d e")
    assert not ok and "5 words" in note and "limit is 3" in note


@pytest.mark.parametrize("reply,expected", [
    ("PASS", (True, "ok")),
    ("PASS: matches", (True, "matches")),
    ("FAIL: too long", (False, "too long")),
    ("**FAIL** - missing name", (False, "missing name")),
    ("Let me think.\nPASS: fine", (True, "fine")),
    ("no idea", (None, "")),
])
def test_parse_verdict(reply, expected):
    assert checker.parse_verdict(reply) == expected


def fake(monkeypatch, reply):
    calls = []

    def f(prompt, model=None, retries=3):
        calls.append(prompt)
        if isinstance(reply, Exception):
            raise reply
        return reply

    monkeypatch.setattr(llm, "call_llm", f)
    return calls


STEP = {"instruction": "Classify.", "output_format": "one_of:a|b", "expected_output": "one word"}


def test_bad_format_skips_verification(monkeypatch):
    calls = fake(monkeypatch, "PASS")
    assert checker.check_step(STEP, "maybe a?") == (False, False, "Expected exactly one of: a, b")
    assert calls == []


def test_good_output_passes(monkeypatch):
    calls = fake(monkeypatch, "PASS: ok")
    assert checker.check_step(STEP, "a", context="ticket text") == (True, True, "ok")
    assert "ticket text" in calls[0] and "Assistant's output:\na" in calls[0]


def test_verifier_fail(monkeypatch):
    fake(monkeypatch, "FAIL: wrong category")
    assert checker.check_step(STEP, "a") == (True, False, "wrong category")


def test_verifier_error_does_not_crash(monkeypatch):
    fake(monkeypatch, RuntimeError("down"))
    fmt_ok, verified, note = checker.check_step(STEP, "a")
    assert fmt_ok and verified and "unavailable" in note


def test_verify_off(monkeypatch):
    calls = fake(monkeypatch, "FAIL")
    assert checker.check_step(STEP, "a", verify=False)[:2] == (True, True)
    assert calls == []


def test_long_verifier_reason_is_truncated():
    ok, reason = checker.parse_verdict("FAIL: " + "word " * 100)
    assert ok is False and len(reason) <= 203
