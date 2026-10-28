"""Offline tests of the arena preset definitions (benchmark/presets_src.py): structure, limits, golden answers,
and an independent recomputation of every number the arithmetic checks expect. No API calls."""
import re
from decimal import Decimal as D, ROUND_CEILING, ROUND_HALF_UP

import pytest

from benchmark import gen_variants as gv
from benchmark.presets_src import PRESET_SPECS
from benchmark.scorer import score_output
from benchmark.tests.golden_presets import GOLDEN_PRESETS
from tools.lint_skill import parse_steps

IDS = [p["id"] for p in PRESET_SPECS]
BY_ID = {p["id"]: p for p in PRESET_SPECS}
LIMITS = {"input": 1500, "skill": 6000, "steps": 6}  # web/arena.py MAX_INPUT, MAX_SKILL, MAX_STEPS


def test_eight_presets_with_unique_ids():
    assert IDS == [f"p0{i}" for i in range(1, 9)]


@pytest.mark.parametrize("preset", PRESET_SPECS, ids=IDS)
def test_structure_and_arena_limits(preset):
    assert {"id", "title", "skill_text", "input", "checks", "steps", "why_it_breaks"} <= set(preset)
    assert "mock" not in preset and "tested" not in preset and "tag" not in preset  # those come from build_presets.py
    assert 0 < len(preset["input"]) <= LIMITS["input"]
    assert 0 < len(preset["skill_text"]) <= LIMITS["skill"]
    steps, _ = parse_steps(preset["skill_text"])  # the same function the arena uses
    assert len(steps) == preset["steps"] <= LIMITS["steps"]
    front = re.match(r"---\nname: ([a-z0-9-]+)\ndescription: (.+)\n---\n", preset["skill_text"])
    assert front, "frontmatter with name and description"
    assert preset["title"].strip() and preset["why_it_breaks"].strip()


@pytest.mark.parametrize("preset", PRESET_SPECS, ids=IDS)
def test_checks_are_valid_for_the_scorer(preset):
    ids = [c["id"] for c in preset["checks"]]
    assert ids == [f"c{i}" for i in range(1, len(ids) + 1)]
    for c in preset["checks"]:
        assert gv.validate_check(c) == [], c


def test_every_preset_has_golden_answers():
    assert set(GOLDEN_PRESETS) == set(IDS)


@pytest.mark.parametrize("preset", PRESET_SPECS, ids=IDS)
def test_good_answers_pass_every_check(preset):
    for out in GOLDEN_PRESETS[preset["id"]]["good"]:
        r = score_output(preset, out)
        assert r["passed"], (r["failed_checks"], r["details"])


@pytest.mark.parametrize("preset", PRESET_SPECS, ids=IDS)
def test_bad_answers_fail_exactly_the_expected_checks(preset):
    for out, expected in GOLDEN_PRESETS[preset["id"]]["bad"]:
        r = score_output(preset, out)
        assert set(r["failed_checks"]) == expected, (out[:70], r["failed_checks"], r["details"])


@pytest.mark.parametrize("preset", PRESET_SPECS, ids=IDS)
def test_every_check_is_exercised_by_a_bad_answer(preset):
    hit = set()
    for _, expected in GOLDEN_PRESETS[preset["id"]]["bad"]:
        hit |= expected
    assert hit >= {c["id"] for c in preset["checks"]}


# --- independent recomputation: the numbers in the checks against code that reads the numbers in the input ---------

def r2(x, places=2):
    return x.quantize(D(1).scaleb(-places), rounding=ROUND_HALF_UP)


def expected_fields(preset_id: str) -> dict:
    """What a correct answer must contain, computed from the numbers in the preset's input text."""
    text = BY_ID[preset_id]["input"]
    nums = lambda s: [D(x) for x in re.findall(r"\d+(?:\.\d+)?", s)]
    if preset_id == "p01":
        items = re.findall(r"(\d+) x [a-z ]+? at (\d+\.\d+)", text)
        sub = sum(D(q) * D(p) for q, p in items)
        disc = r2(sub * D("0.12")) if sub > 150 else D("0.00")
        tax = r2((sub - disc) * D("0.075"))
        return {"subtotal": str(sub), "discount": str(disc), "tax": str(tax), "total": str(sub - disc + tax)}
    if preset_id == "p04":
        a = r2(nums(text)[0] * D("0.80")); b = r2(a * D("0.85")); t = r2(b * D("0.08"))
        return {"price_a": str(a), "price_b": str(b), "tax": str(t), "final": str(b + t)}
    if preset_id == "p05":
        bal, over = nums(text.split("Transactions")[0].split("balance")[1])[0], 0
        for kind, amt in re.findall(r"(withdraw|deposit) (\d+\.\d+)", text):
            bal = bal - D(amt) if kind == "withdraw" else bal + D(amt)
            if kind == "withdraw" and bal < 0:
                bal -= D("12.00"); over += 1
        return {"final_balance": str(bal), "overdrafts": str(over)}
    if preset_id == "p06":
        quizzes = [D(x) for x in re.findall(r"\d+", text.split("Project")[0])]
        project, exam = (D(x) for x in re.findall(r"\d+", text.split("Project")[1]))
        kept = sorted(quizzes)[1:]; qa = sum(kept) / len(kept)
        w = (D("0.2"), D("0.3"), D("0.5")) if exam > qa else (D("0.3"), D("0.3"), D("0.4"))
        grade = r2(qa * w[0] + project * w[1] + exam * w[2], 1)
        return {"quiz_average": str(r2(qa, 1)), "final_grade": str(grade),
                "letter": "A" if grade >= 90 else "B" if grade >= 80 else "C" if grade >= 70 else "D" if grade >= 60 else "F"}
    if preset_id == "p07":
        weight, dist = nums(text)[0], nums(text)[1]
        started = int((max(weight - 1, D(0)) / D("0.5")).to_integral_value(rounding=ROUND_CEILING))
        fee = D("4.50") + started * D("1.20"); sur = D("2.00") if dist > 100 else D("0.00")
        vat = r2((fee + sur) * D("0.10"))
        return {"weight_fee": str(fee), "surcharge": str(sur), "vat": str(vat), "total": str(fee + sur + vat)}
    raise KeyError(preset_id)


@pytest.mark.parametrize("preset_id", ["p01", "p04", "p05", "p06", "p07"])
def test_json_presets_expect_the_independently_computed_numbers(preset_id):
    import json
    want = expected_fields(preset_id)
    good = json.loads(GOLDEN_PRESETS[preset_id]["good"][0])
    assert {k: str(v) for k, v in good.items()} == want
    checked = " ".join(c["value"] for c in BY_ID[preset_id]["checks"] if c["type"] == "regex")
    for key, value in want.items():
        if key == "overdrafts":
            assert re.search(rf'"{key}"\\s\*:\\s\*{value}', checked)
        else:
            assert re.escape(value) in checked or value in checked, (key, value)


def test_p02_time_arithmetic_recomputed():
    # 21:40 + 9h35 = 31:15 in Lisbon's clock; 5 hours behind = 26:15; 24:00 or later -> 02:15, next day
    mins = 21 * 60 + 40 + 9 * 60 + 35 - 5 * 60
    assert (mins >= 1440, f"{mins % 1440 // 60:02d}:{mins % 60:02d}") == (True, "02:15")


def test_p03_scaling_recomputed():
    f = D(24) / D(6)
    scaled = {"beans": 900 * f, "tomatoes": 1200 * f, "beef": 450 * f, "oil": 3 * f, "salt": D("1.2") * f}
    shown = {k: (f"{r2(v / 1000, 1)} kg" if k in ("beans", "tomatoes", "beef") else f"{r2(v, 1)}") for k, v in scaled.items()}
    assert shown == {"beans": "3.6 kg", "tomatoes": "4.8 kg", "beef": "1.8 kg", "oil": "12.0", "salt": "4.8"}
    assert f == 4
