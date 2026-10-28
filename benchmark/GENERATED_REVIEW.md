# Hand-check of generated tasks

| | |
|---|---|
| Reviewer | Likhitha |
| Date | 2026-10-28 |
| Generated tasks | 25 valid (30 asked for, 5 dropped at schema validation) |
| Review sample | 12 random tasks out of the 25 valid ones (seed 1, `python -m benchmark.gen_variants --review 12`) |
| Sample ids | t01-v2, t01-v3, t03-v1, t03-v2, t04-v2, t04-v3, t05-v1, t06-v2, t07-v2, t07-v3, t08-v3, t09-v1 |

**5 of the 12 reviewed generated tasks (42%) had broken or ambiguous checks.**

**The other 13 tasks are NOT reviewed and stay excluded; they must not be used in any reported result:** t01-v1, t03-v3, t05-v2, t05-v3, t06-v1, t06-v3, t08-v1, t08-v2, t09-v2, t09-v3, t10-v1, t10-v2, t10-v3.

## Kept (7)

t01-v2, t01-v3, t05-v1, t06-v2, t07-v2, t07-v3, t08-v3.

## Dropped after hand-check (5)

- **t04-v2:** subtotal expected 161.55, but 15 x 1.15 + 12 x 12.10 = 162.45. Discount expected 16.16, but 162.45 is under the 200 threshold, so the discount is 0.00.
- **t04-v3:** subtotal 110.00 is right, but it is under 200, so the discount is 0.00, not 11.00. Tax and total are therefore wrong too.
- **t03-v1:** the input says 6 years, but its own dates give about 8 years, so the check (years = 6) contradicts the input.
- **t03-v2:** ambiguous. The skill needs "the skill Python in the resume", but the input mentions Python only as used in 2015 and no longer used. A reasonable answer could be yes or no.
- **t09-v1:** the input date 03/05/2027 does not say whether it is DD/MM or MM/DD, so the closing-date check may fail a correct answer. The "Sweden" check also covers only the summary field.

## Dropped earlier, at schema validation (5)

`gen_variants` dropped 5 variants before the hand-check (details in `output/generated/dropped_variants.json`):

- t02 x 3: check label `hard_limit_violation` is not one of the 7 labels.
- t04 x 1 and t07 x 1: invalid difficulty tag.

## Edits made after review (2)

Only generated tasks were edited, in `tasks_generated.json` and carried into `tasks_generated_reviewed.json`. `tasks.json` (the frozen hand-written tasks) was not touched.

**1. t08-v3, check c5 (scale factor line)** now accepts "10" or "10.0":

- before: `(?m)^Scale factor:\s*10\s*\Z`
- after: `(?m)^Scale factor:\s*10(\.0)?\s*\Z`

**2. t05-v1, checks c4 to c7 (subtotal, discount, tax, total).** The only change is that the two literal quote characters were removed from each regex. Why: each check also has a `path`, so it is matched against the unquoted field value (`441.60`), and a pattern that requires literal quote characters could never match, not even the correct answer. The golden check found this: the correct answer failed c4 to c7.

| Check | Field | Old regex | New regex |
|---|---|---|---|
| c4 | subtotal | `"441\.60"` | `441\.60` |
| c5 | discount | `"44\.16"` | `44\.16` |
| c6 | tax | `"31.80"` | `31.80` |
| c7 | total | `"429.24"` | `429.24` |

Nothing else changed (verified field by field: exactly these four `value` fields differ, and all 25 tasks are still present).

## Reviewed file

| | |
|---|---|
| File | `benchmark/tasks_generated_reviewed.json` (the 7 kept tasks only) |
| SHA-256 | `3b0d781b32ac77a3c32f34d7bac6397e5c5d78b98a2bf431a016c90bb7da7e5b` |
| Written and frozen | 2026-10-28 17:00 +0530 |
| Previous SHA-256 (before the t05-v1 edit, never used in a run) | `c965bf6f8f304cbb451a7e4f1124c154e0e88b8082159d3f2f2cb4fea189cde7`, written 2026-10-28 16:51 +0530 |
| Status | **Frozen before any run. Never edit, add or drop tasks after seeing results.** |

A test (`tests/test_generated_tasks.py`) checks that this hash matches the file on disk.

## Golden check (hand-worked answers, `tests/golden_generated.py`)

Each of the 7 tasks has a hand-worked correct answer that passes every check, and wrong answers that fail exactly the expected check; every check is exercised by at least one wrong answer. All pass.

- **t05-v1:** before the edit above, its correct answer failed c4 to c7. After the edit the correct answer passes, and each wrong answer fails exactly one check (invoice, subtotal, discount, tax or total), with no cascade.
- **t07-v2 whitespace:** the scorer strips leading and trailing whitespace (spaces, tabs, blank lines) before the exactly-4-lines check, so those pass. A blank line inside the answer, a 5th line, or text before the first line fails c5.

## Known limits (kept, not changed)

- **t01-v3 c3** (`fix` must not contain "just") has no whole-word flag, so it matches inside words: a fix such as "Adjust the payment button state." fails it.
- **t07-v2** fails an answer with Windows line endings (CRLF), because `$` does not match before a carriage return (c1 to c3 fail).
- **Some regexes use an unescaped dot** (t06-v2 c1 to c3, t05-v1 c6 and c7), which matches any character.
- **t05-v1 c4 to c7 are now unanchored patterns** (no `^` or `$`), so they match inside a longer value, for example `441.601` would still satisfy c4.
- **The generated checks verify selected values, not complete answers:** t06-v2 does not require the chili row, t08-v3 does not require the table header, t07-v3 does not forbid extra lines, and t07-v2 does not check the order of its four lines. A pass means the checked values were right.
- **Resuming a run after its overrides file changes** can leave old labels on already-completed tasks (not triggered in our runs).
- **These limits were left unchanged** because the reviewed file was frozen before any run.
