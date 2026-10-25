import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import lint_skill as L  # noqa: E402

CLEAN = """---
name: clean
description: x
---
1. Extract the customer's first name.
2. Classify the ticket as exactly one of: billing, technical, account.
3. Draft a reply of at most 60 words.
4. Output everything as JSON with keys: name, category, reply.
"""

LONG = "---\nname: long\ndescription: x\n---\n" + "\n".join(
    f"{i}. Do unrelated action number {i} with item {chr(96 + i)} and report the list." for i in range(1, 14)
)

SIMILAR = """1. Summarize the ticket in one sentence.
2. Summarize the customer's request in one sentence.
3. Output a list of both summaries.
"""

VAGUE = """1. Read the input and respond appropriately, as needed.
2. If it is long and if it is angry, reply properly unless it is spam, then stop. After that, relax.
3. Add relevant details etc.
"""


def rules(text):
    return {f["rule"] for f in L.lint(text)["findings"]}


def test_clean_skill_is_low_risk():
    r = L.lint(CLEAN)
    assert r["level"] == "low" and r["score"] < 25 and r["findings"] == []
    assert r["steps"] == 4


def test_long_skill_flags_step_count():
    r = L.lint(LONG)
    assert "L01" in rules(LONG)
    assert any("above 12" in f["message"] for f in r["findings"])


def test_similar_steps_flagged_on_second_step():
    f = [x for x in L.lint(SIMILAR)["findings"] if x["rule"] == "L03"]
    assert f and f[0]["step"] == 2


def test_vague_skill_hits_vague_multi_condition_rules():
    got = rules(VAGUE)
    assert {"L04", "L05", "L06", "L07"} <= got
    assert L.lint(VAGUE)["level"] in ("medium", "high")


def test_long_step_flagged():
    text = "1. " + " ".join(["word"] * 70) + "\n2. Output JSON.\n"
    assert "L02" in rules(text)


def test_unnumbered_headings_flag_l08():
    text = "## Read the ticket\nRead it.\n\n## Output\nOutput JSON.\n"
    r = L.lint(text)
    assert r["steps"] == 2 and "L08" in rules(text)


def test_paragraph_fallback():
    steps, numbered = L.parse_steps("Read the ticket.\n\nReply in a list.\n")
    assert len(steps) == 2 and not numbered


def test_wrapped_numbered_step_is_joined():
    steps, _ = L.parse_steps("1. First part\n   second part\n2. Next\n")
    assert steps[0] == "First part second part"


def test_json_cli(tmp_path, capsys):
    p = tmp_path / "SKILL.md"
    p.write_text(CLEAN, encoding="utf-8")
    assert L.main([str(p), "--json"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert set(data) >= {"score", "level", "findings"}


def test_text_cli(tmp_path, capsys):
    p = tmp_path / "SKILL.md"
    p.write_text(VAGUE, encoding="utf-8")
    L.main([str(p)])
    assert "Risk for small models" in capsys.readouterr().out


def test_score_is_capped_at_100():
    assert L.lint(LONG + "\n".join(["use appropriate etc"] * 0))["score"] <= 100


def test_frontmatter_stops_at_line_that_is_exactly_dashes():
    text = "---\nname: x\ndescription: a --- b\n---\n1. First step\n2. Output as JSON\n"
    assert L.strip_frontmatter(text).startswith("1. First step")
    assert L.lint(text)["steps"] == 2


def test_frontmatter_not_stripped_when_not_first_line():
    text = "# Title\n---\n1. A\n"
    assert L.strip_frontmatter(text) == text


def test_unclosed_frontmatter_is_left_alone():
    text = "---\n1. A\n2. B\n"
    assert L.strip_frontmatter(text) == text


def test_frontmatter_with_crlf_line_endings():
    assert L.strip_frontmatter("---\r\nname: x\r\n---\r\n1. A\r\n").startswith("1. A")


def test_no_steps_scores_above_low_threshold():
    for text in ("", "   \n", "# Title only\n"):
        r = L.lint(text)
        assert r["steps"] == 0
        assert "L09" in {f["rule"] for f in r["findings"]}
        assert r["score"] > 25 and r["level"] != "low"
