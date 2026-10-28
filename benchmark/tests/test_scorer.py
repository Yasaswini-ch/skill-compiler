"""Tests for benchmark/scorer.py. No API key and no network needed."""
import pytest

from benchmark.scorer import score_output, strip_fences

LABELS = "wrong_format"


def run(check: dict, output: str) -> dict:
    check = {"id": "c1", "label": LABELS, **check}
    return score_output({"checks": [check]}, output)


def passes(check: dict, output: str) -> bool:
    return run(check, output)["passed"]


# (check, passing outputs, failing outputs): at least 2 of each per check type.
CASES = [
    ({"type": "json_valid"},
     ['{"a": 1}', '[1, 2]'],
     ['{"a": 1', 'not json at all']),
    ({"type": "json_keys", "value": ["a", "b"]},
     ['{"a": 1, "b": 2}', '{"b": 2, "a": 1}'],
     ['{"a": 1}', '{"a": 1, "b": 2, "c": 3}', '[1, 2]']),
    ({"type": "one_of", "path": "cat", "value": ["billing", "technical"]},
     ['{"cat": "billing"}', '{"cat": " technical "}'],
     ['{"cat": "Billing"}', '{"cat": "it is billing"}', '{"cat": 3}']),
    ({"type": "max_words", "value": 5},
     ["one two three four five", "  hello  "],
     ["one two three four five six", "a b c d e f g h"]),
    ({"type": "min_words", "value": 3},
     ["one two three", "a b c d e"],
     ["one two", ""]),
    ({"type": "starts_with", "value": "Hi Ravi,"},
     ["Hi Ravi, thanks.", "  Hi Ravi, ok"],
     ["Hello Ravi,", "hi Ravi,"]),
    ({"type": "contains", "value": "refund"},
     ["We will REFUND you", "a refund is due"],
     ["we will repay you", ""]),
    ({"type": "not_contains", "value": "sorry"},
     ["Thanks for waiting", "We apologise"],
     ["I am Sorry about that", "so sorry"]),
    ({"type": "regex", "value": r"^\d{3}-\d{4}$"},
     ["555-1234", "000-9999"],
     ["5551234", "555-12345"]),
    ({"type": "order", "value": ["alpha", "beta", "gamma"]},
     ["alpha then beta then gamma", "alpha beta gamma gamma"],
     ["beta alpha gamma", "alpha gamma"]),
]


@pytest.mark.parametrize("check,good,bad", CASES, ids=[c[0]["type"] for c in CASES])
def test_each_check_type(check, good, bad):
    assert len(good) >= 2 and len(bad) >= 2
    for out in good:
        assert passes(check, out), f"should pass: {out!r} -> {run(check, out)['details']}"
    for out in bad:
        assert not passes(check, out), f"should fail: {out!r}"


def test_every_check_type_has_cases():
    from benchmark.scorer import CHECKS
    assert {c[0]["type"] for c in CASES} == set(CHECKS)


def test_not_contains_whole_word():
    chk = {"type": "not_contains", "value": "sorry", "whole_word": True}
    assert passes(chk, "sorrow and sorries")
    assert not passes(chk, "I am sorry.")


def test_case_sensitive_contains():
    chk = {"type": "contains", "value": "JSON", "case_sensitive": True}
    assert passes(chk, "valid JSON")
    assert not passes(chk, "valid json")


def test_strip_fences():
    assert strip_fences('```json\n{"a": 1}\n```') == '{"a": 1}'
    assert strip_fences('```\nplain\n```') == "plain"
    assert strip_fences('  ```json\n{"a": 1}\n```  ') == '{"a": 1}'
    assert strip_fences("no fence") == "no fence"
    assert strip_fences("Here you go:\n```json\n{}\n```") != "{}"  # prose before a fence is not stripped


def test_fenced_json_passes_json_checks():
    out = '```json\n{"name": "Ravi", "reply": "Hi Ravi, ok"}\n```'
    task = {"checks": [
        {"id": "c1", "type": "json_valid", "label": "wrong_format"},
        {"id": "c2", "type": "json_keys", "value": ["name", "reply"], "label": "skipped_step"},
        {"id": "c3", "type": "starts_with", "path": "reply", "value": "Hi ", "label": "ignored_constraint"},
    ]}
    assert score_output(task, out)["passed"]


def test_path_dot_notation_and_list_index():
    out = '{"a": {"b": ["x", "y z"]}}'
    assert passes({"type": "max_words", "path": "a.b.1", "value": 2}, out)
    assert not passes({"type": "max_words", "path": "a.b.1", "value": 1}, out)
    assert passes({"type": "one_of", "path": "a.b.0", "value": ["x"]}, out)


def test_path_missing_has_clear_reason():
    r = run({"type": "max_words", "path": "reply", "value": 5}, '{"name": "x"}')
    assert not r["passed"]
    assert "not found" in r["details"]["c1"]


def test_path_on_non_json_output_has_clear_reason():
    r = run({"type": "max_words", "path": "reply", "value": 5}, "plain text")
    assert not r["passed"]
    assert "not valid JSON" in r["details"]["c1"]


def test_json_keys_on_non_json_fails_clearly():
    r = run({"type": "json_keys", "value": ["a"]}, "plain text")
    assert not r["passed"] and "not valid JSON" in r["details"]["c1"]


def test_json_keys_reports_missing_and_extra():
    r = run({"type": "json_keys", "value": ["a", "b"]}, '{"a": 1, "z": 2}')
    assert "missing keys ['b']" in r["details"]["c1"] and "extra keys ['z']" in r["details"]["c1"]


def test_json_keys_with_path_checks_nested_object():
    assert passes({"type": "json_keys", "path": "u", "value": ["rating", "reason"]},
                  '{"u": {"rating": 5, "reason": "x"}}')
    assert not passes({"type": "json_keys", "path": "u", "value": ["rating"]},
                      '{"u": {"rating": 5, "reason": "x"}}')


def test_numbers_in_json_are_checked_as_text():
    assert passes({"type": "regex", "path": "n", "value": r"^3$"}, '{"n": 3}')


def test_first_failed_check_decides_label_and_all_failures_listed():
    task = {"checks": [
        {"id": "c1", "type": "json_valid", "label": "wrong_format"},
        {"id": "c2", "type": "max_words", "value": 2, "label": "ignored_constraint"},
        {"id": "c3", "type": "contains", "value": "zzz", "label": "skipped_step"},
    ]}
    r = score_output(task, "one two three")
    assert r["failed_checks"] == ["c1", "c2", "c3"]
    assert r["failure_label"] == "wrong_format"
    assert r["passed"] is False
    assert r["details"]["c1"] == "output is not valid JSON"
    assert r["details"]["c2"] == "3 words; the limit is 2"


def test_all_pass_has_no_label():
    r = score_output({"checks": [{"id": "c1", "type": "contains", "value": "a", "label": "other"}]}, "a")
    assert r == {"passed": True, "failed_checks": [], "failure_label": None, "details": {"c1": "ok"}}


def test_missing_label_defaults_to_other():
    r = score_output({"checks": [{"id": "c1", "type": "contains", "value": "zzz"}]}, "a")
    assert r["failure_label"] == "other"


def test_unknown_type_and_bad_regex_fail_instead_of_raising():
    assert "unknown check type" in run({"type": "nope"}, "x")["details"]["c1"]
    assert "bad check definition" in run({"type": "regex", "value": "("}, "x")["details"]["c1"]


def test_empty_output():
    assert not passes({"type": "json_valid"}, "")
    assert not passes({"type": "min_words", "value": 1}, "")


def test_json_keys_label_extra_keys_only_is_wrong_format():
    task = {"checks": [{"id": "c1", "type": "json_keys", "value": ["a", "b"], "label": "skipped_step"}]}
    r = score_output(task, '{"a": 1, "b": 2, "z": 3}')
    assert r["failed_checks"] == ["c1"] and r["failure_label"] == "wrong_format"


def test_json_keys_label_missing_keys_is_skipped_step():
    task = {"checks": [{"id": "c1", "type": "json_keys", "value": ["a", "b"], "label": "wrong_format"}]}
    r = score_output(task, '{"a": 1}')
    assert r["failed_checks"] == ["c1"] and r["failure_label"] == "skipped_step"


def test_json_keys_label_missing_wins_over_extra():
    task = {"checks": [{"id": "c1", "type": "json_keys", "value": ["a", "b"], "label": "other"}]}
    assert score_output(task, '{"a": 1, "z": 3}')["failure_label"] == "skipped_step"


def test_json_keys_non_json_keeps_the_task_label():
    task = {"checks": [{"id": "c1", "type": "json_keys", "value": ["a"], "label": "other"}]}
    assert score_output(task, "plain text")["failure_label"] == "other"


def test_json_keys_label_applies_only_when_it_is_the_first_failure():
    task = {"checks": [{"id": "c1", "type": "contains", "value": "zzz", "label": "ignored_constraint"},
                       {"id": "c2", "type": "json_keys", "value": ["a"], "label": "skipped_step"}]}
    assert score_output(task, '{"a": 1, "b": 2}')["failure_label"] == "ignored_constraint"
