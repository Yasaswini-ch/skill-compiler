# Harness notes (`skillcompiler/`)

Design, usage and findings for the harness, written by the harness owner (Person A).
The one-page quickstart lives in [`skillcompiler/README.md`](../skillcompiler/README.md).

> Every number in this file comes from a real run on the date it was measured
> (24 and 25 Oct 2026, model `gemma-4-26b-a4b-it` unless stated). Unless a table says otherwise it is a **single run**.
> They show that the harness works. They are **not** benchmark results. The benchmark is in `benchmark/`.

## 1. What it does

A long skill (`SKILL.md`) is hard for a small model to follow in one go. The harness:

1. **Splits** the skill into small ordered steps (`plan.json`).
2. **Runs** one step per model call, passing the original input and the outputs of the steps it depends on.
3. **Checks** each output (format first, then rules from the instruction, then a model PASS/FAIL).
4. **Retries** a failed step with the rejected answer and the checker's note as feedback.
5. **Writes** a `trace.json` describing every attempt.

```
SKILL.md -> splitter -> plan.json -> runner -> [ step prompt -> model -> checker ] x N -> trace.json
                                                    ^                      |
                                                    +---- retry + note ----+  (up to max_retries)
```

## 2. Modules

| File | Role |
|---|---|
| `llm.py` | `call_llm()` with 3 tries and exponential backoff; counts calls, latency, errors, cache hits (`llm.stats`). |
| `splitter.py` | `compile_skill()`: model plan first (one retry on bad JSON), rule-based fallback (numbered list, then headings, then paragraphs). `validate_steps()` enforces the contract. A coverage check compares the plan with the skill: every number and quoted phrase in the skill must appear somewhere in the plan, otherwise the model gets one retry listing what is missing, and any leftover is recorded in an optional `warnings` list in the plan (the CLI prints it). |
| `checker.py` | `check_step()` returns `(format_ok, verified, note)`. See section 4. |
| `runner.py` | `run_skill()`: the step loop, prompts, retries, trace. |
| `plan_io.py` | `save_plan()` / `load_plan()` for `.json`, `.yaml`, `.yml`. Loading validates. |
| `cache.py` | Disk cache of model responses (`--cache`, `--replay`). |
| `providers.py` | `gemini` (default) or `openai-compatible` (Ollama, vLLM, llama.cpp). |
| `__main__.py` | CLI: `compile` and `run`. |
| `examples/` | Three sample skills with inputs (6, 8 and 12 steps). |
| `tests/` | 104 tests; none needs an API key. |

## 3. How one step runs

Prompt = step title, instruction, expected output, a plain-words format hint, the original input, and
the outputs of the steps in `depends_on`. On a retry the prompt adds the rejected answer and the checker's note.

Status in the trace:

- `pass`: accepted on the first attempt.
- `repaired`: accepted after at least one retry.
- `fail`: still rejected after `max_retries` retries (default 2, so 3 attempts). The run continues, and the last output is passed on.

A model call that fails after its own backoff is recorded as a failed attempt. It never crashes the run.
`final_output` is the last step's output.

## 4. The checker, in order

1. **Format** (no model call), from the step's `output_format`:
   `text` (non-empty), `json` (code fences allowed), `list` (bullets, numbered, several lines, a JSON array, or comma-separated),
   `number`, `one_of:a|b|c` (case and punctuation ignored), `max_words:N`. Unknown formats pass.
2. **Rules in the instruction** (no model call): `must begin/start with "X"` (a `<placeholder>` inside X matches any text)
   and `must not contain the word/phrase "Y"`. Skipped for `json` steps, whose wording rules are left to the verifier.
3. **Verifier** (one model call): replies `PASS` or `FAIL: reason`. It is told to fail only a clear violation and to pass when several answers are reasonable. Reasons are cut to 200 characters.

A failure in 1 or 2 skips step 3. The note is the retry feedback, for example `Output has 94 words; the limit is 60`.
If the verifier call errors, or its reply has no PASS/FAIL, the step is **accepted** and the note says so (`verifier unavailable, accepted ...`).
`--no-verify` runs steps 1 and 2 only.

## 5. Command line

```bash
python -m skillcompiler compile skillcompiler/examples/ticket-triage/SKILL.md -o plan.yaml
python -m skillcompiler run skillcompiler/examples/ticket-triage/SKILL.md \
    --input-file skillcompiler/examples/ticket-triage/input.txt --plan plan.yaml --trace trace.json
```

| Flag | Applies to | Meaning |
|---|---|---|
| `-o PATH` | compile | Write the plan (format by extension). Without it the plan is printed. |
| `--input-file PATH` / `--input TEXT` | run | The user input (one is required). |
| `--plan PATH` | run | Use a saved plan and skip the split call. The `SKILL.md` argument is still required. |
| `--trace PATH` | run | Write `trace.json`. The final answer always goes to stdout. |
| `--model NAME` | both | Overrides `GEMMA_MODEL`. |
| `--max-retries N` | run | Retries per step (default 2). |
| `--no-verify` | run | Skip the verifier call. |
| `--mode full\|adaptive\|auto` | run | `full` (default): model verifier on every step. `adaptive`: verifier only on risky steps. `auto`: lint first, run easy skills plain, the rest adaptive (section 13). Env `SKILLCOMPILER_MODE`; the flag wins. |
| `--escalate-model NAME` | run | A step that still fails after its retries gets one last attempt on this bigger model (section 13). |
| `--cache` / `--replay` / `--cache-dir DIR` | both | See section 6. |
| `--provider`, `--base-url URL` | both | See section 7. |

Progress lines go to stderr, so `stdout` can be piped. A missing file, missing `.env` or bad plan prints a short `error:` line and exits with code 1.

Environment (`.env` in the repo root, never committed): `GEMINI_API_KEY`, `GEMMA_MODEL`,
optional `GEMMA_THINKING`, `GEMMA_RPM`, `GEMMA_TIMEOUT` (seconds per request, default 240), `SKILLCOMPILER_MODE`, `SKILLCOMPILER_COPY_RULE` (section 13) and `SKILLCOMPILER_VERIFY=0` (turns the verifier call off for every run; an explicit `verify=` argument or `--no-verify` still wins), `OPENAI_API_KEY` and `OPENAI_BASE_URL` for the other provider.

From Python:

```python
from skillcompiler import run_skill, compile_skill
plan = compile_skill(skill_text)                                   # plan.json dict
trace = run_skill(skill_text, user_input, model=None,              # trace.json dict
                  max_retries=2, verify=True, plan=None)
```

## 6. Cache and replay (the demo backup)

`--cache` stores each response under `.skillcompiler_cache/` (or `--cache-dir`), keyed by a hash of (provider, model, prompt).
A cache hit costs 0 calls. `--replay` serves only from the cache and **never calls the API**: it works offline,
and a miss stops with `replay mode: this prompt is not in the cache ... Run once with --cache first.`

Measured on `ticket-triage` with a YAML plan: first run 12 calls, 25.1 s; replay 0 calls, 0.75 s, 12 cache hits, same result.

To prepare a demo: run the exact demo inputs once with `--cache`, keep that folder, then rehearse with `--replay`.
Replay only matches prompts that are byte-identical, so changing a skill, an input or a prompt template needs a fresh cached run.
The cache folder is not in `.gitignore`.

## 7. Other models

```bash
python -m skillcompiler run SKILL.md --input-file in.txt \
    --provider openai-compatible --base-url http://localhost:11434/v1 --model gemma3:4b
```

Plain HTTP to `<base-url>/chat/completions` (no extra dependency, no Gemini key needed). Inline reasoning blocks
(`<thought>`, `<think>`) are stripped from replies, because they would break the format checks.

## 8. Findings during development

These are the real problems the live runs exposed, and what was changed. All are covered by tests.

| Finding | Evidence | Change |
|---|---|---|
| **Thinking made calls very slow.** Gemma 4 spends hidden "thinking" tokens. | A splitter call on `gemma-4-26b-a4b-it` used 6,770 thinking tokens for 678 answer tokens and took 158 s. Short prompts took 3 to 5 s. | `llm.py` sends `thinking_level="MINIMAL"` by default: the same call took 14 to 19 s. `thinking_budget` and `LOW` are rejected by this model. `GEMMA_THINKING=default` restores the model's own setting. Quality check: see the thinking comparison in section 9. |
| `gemma-4-31b-it` was no better. | 104 s on the same prompt, and 3 of 6 calls returned HTTP 500. | Stayed on the 26b model. |
| **The model copied the format label.** | For `one_of:shipping|quality|billing|other` it answered `one_of:quality`, twice. | The prompt now describes the format in words ("exactly one of these values and nothing else: ..."). |
| **The verifier was too strict and too wordy.** | It rejected `shipping` where `quality` was equally arguable, and its rambling reason became the retry feedback. | Verifier prompt: fail only clear violations, pass if several answers are reasonable, 25 words. Reasons are cut to 200 characters. |
| **A begin-with rule was missed.** | `Internal note:` prefix dropped and the verifier passed it. | `check_constraints()` enforces begin-with and forbidden-word rules without a model call. |
| **A correct answer was rejected.** | The skill asked for comma-separated names; the `list` check wanted one per line. | `list` accepts comma-separated items; the prompt hint no longer dictates a layout. |
| **Free-tier rate limit.** The API allows **30 requests per minute per model**; a 12-step skill makes about 25 calls, and back-to-back runs exceeded the limit (HTTP 429, "retry in 48s"). | A 429 mid-run made the verifier unavailable for one step. | `llm.py` has a sliding-window limiter (default 25 requests per minute, `GEMMA_RPM=0` turns it off) and, on a 429, waits for the server's own "retry in Ns" hint (cap 70 s). Applies to the `gemini` provider only. |
| **The verifier made a correct answer worse.** | On `2 x 3.50 + 4 x 1.25 + 8.00` the model answered `20.00` (correct); the verifier rejected it twice with wrong arithmetic, the model switched to `19.00`, and that was accepted. In another task it flip-flopped on an ambiguous label (`travel`, `other`, `travel`). | If the model gives an answer it already gave earlier in the same step and only the verifier objects, the answer is kept (step status `repaired`, note `model repeated its answer; verifier objection overruled`). A format or rule failure is never overruled. |
| **A rule for the final answer did not reach the last step.** | Skill said the text must begin with "Meet the"; the final text began "Meet this" and every step passed. | The splitter prompt now says to repeat rules that apply to the final answer in the last step's instruction. This relies on the model following it. |
| **Run counters were global.** | Two runs at once (live mode, a web server) would have mixed their `totals`. | `llm.stats` is now kept per thread. |
| **The verifier overrule hid a real failure.** | Post-benchmark run, task t04: the verifier rejected the final JSON twice, correctly (it contradicted the earlier steps). The model then flip-flopped back to its first wrong answer and the old rule ("the model gave this answer before") accepted it as `repaired`. | The overrule now covers only the **same answer twice in a row**. The flip-flop stays a failure. The old rule fired in none of the 37 official and repeat harness traces, so the official behaviour is unchanged. |
| **The final JSON step changed a value's type.** | Benchmark task t03 failed in all three official runs: step 5 produced the text `no`, and the final "format JSON" step wrote `false`. The checker only verifies valid JSON. | A rule for JSON steps that combine earlier results: copy each exactly and keep its type. **Off by default** (`SKILLCOMPILER_COPY_RULE=1`): it passed t03 3 of 3 re-runs, but it was written after seeing the failure and a full re-run was mixed (section 13), so the default stays as in the official runs. |
| **A run once hung on one call, with no error** (benchmark run 2). | The Gemini client had no request timeout. Cause not proven. | `GEMMA_TIMEOUT` sets a per-request limit (default 240 s). The stream also has a whole-run `timeout_s` (section 13). |
| **A missing API key was retried with delays.** | `os.environ["GEMINI_API_KEY"]` raised inside the retry loop. | It is now a `ConfigError`: no retry, a clear message. |
| The splitter sometimes adds small wording. | One plan added "Use the rating and reason from step 3" to the final step. | Not changed. The plan can be saved and edited (`compile -o`, then `--plan`). |

## 9. Live runs of the examples (single runs, after all the changes above)

| Skill | Steps | Result | Retries | Calls | Time |
|---|---|---|---|---|---|
| `ticket-triage` | 6 | 6 pass | 0 | 12 | 31 s |
| `meeting-minutes` | 8 | 8 pass | 0 | 15 | 48 s |
| `complaint-resolution` | 12 | 11 pass, 1 repaired (sentiment) | 1 | 25 | 90 s |

Calls per run are about 2 per step (one answer, one verification) plus one for the split, so a run costs
roughly `2N + 1` calls. Runs are not deterministic: early on, `ticket-triage` repaired its classify step; after the fixes in section 8 it passed every step in 5 of 5 repeated runs.

**Stress test (informal, 24 Oct, one run each, not part of the repo).** Five tasks written to resemble the benchmark's difficulty types
(similar-sounding steps with strict JSON, a fixed table, step order, hard word and wording limits, a skill with headings and no numbers),
each checked by a short script and run through the harness and as one plain call.
After the fixes above the harness passed all 5 and plain Gemma passed 3 (it failed the table total and the step-order arithmetic).
The checks were written by the harness author and the sample is five runs, so this shows the harness behaves sensibly on varied skills
and does not show how much it helps. That measurement belongs to `benchmark/`. Before the fixes the same test exposed the rate-limit,
verifier and final-rule problems in section 8, and the harness did not crash on any task.

**Repeated runs (5 per skill, 25 Oct, default settings: thinking MINIMAL, verifier on).**

| Skill | Runs | Steps passing first try | Repaired | Failed | Final output valid JSON | Calls per run | Time per run |
|---|---|---|---|---|---|---|---|
| `ticket-triage` (6 steps) | 5 | 30 of 30 | 0 | 0 | 5 of 5 | 13 | 35 to 50 s |
| `meeting-minutes` (8 steps) | 5 | 40 of 40 | 0 | 0 | 5 of 5 | 17 | 47 to 57 s |
| `complaint-resolution` (12 steps) | 5 | 59 of 60 | 1 | 0 | 5 of 5 | 24 to 26 | 61 to 64 s (one run 112 s) |

These skills are the ones the prompts and checks were tuned on, so the clean rates are optimistic for unseen skills.
They show the harness is stable on them, not how much it helps compared with plain Gemma. (One timing, 5,444 s, was a laptop sleeping and is left out.)

**Thinking MINIMAL vs the model's default (the five stress tasks, one run each, 25 Oct).** Harness with MINIMAL: 5 of 5 pass, 51 calls, 146 s in total.
Harness with default thinking: 5 of 5 pass, 57 calls, 1,220 s in total (about 8 times slower). Plain Gemma passed all 5 under both settings in these runs
(it had failed two of them in earlier runs), so these tasks do not separate the settings or separate plain from the harness.
What this supports: MINIMAL does not visibly hurt on these five tasks and is much faster. It does not show that default thinking could never help on a harder task.

**Verifier on or off (same five stress tasks, one run each).** With the verifier on: 5 of 5 pass my checks, 63 model calls, about 185 s.
With it off (`--no-verify`, format and rule checks only): 5 of 5 pass, 30 calls, about 118 s. Plain Gemma passed 3 of 5 in the first run and 4 of 5 in the second
(it passed the step-order task the second time), so single runs are noisy. These tasks are mostly format and wording rules, which the format and rule checks
still enforce without the verifier, so this does not show what the verifier catches on wrong-but-well-formed answers. It did catch a wrong category in an
earlier manual test, and it also caused the errors in section 8. Use `SKILLCOMPILER_VERIFY=0` when the rate limit matters more than semantic checking,
and say so when quoting numbers.

**Another open model.** `ticket-triage` on a local Ollama `gemma3:4b` (before the last two checker changes, so not directly comparable):
3 of 6 steps failed after 3 attempts each, 22 calls, 345 s, and the final JSON had `"category": "billing|technical"`.
So the harness runs on another model, but it does not make every model reliable.

## 10. Known limitations

- **It costs more.** About `2N + 1` calls and tens of seconds per skill, against one call without the harness (see `benchmark/overhead.md` when available).
- **A model verifier can be wrong** in both directions. A verifier outage is accepted (the trace note says so), and a repeated answer overrules the verifier, so a stubborn wrong answer can be accepted.
- **The splitter coverage check is narrow.** It looks only at digits and quoted phrases (not number words such as "sixty", and not meaning), and on the eight skills tried so far the model's first plan always passed it, so the retry path has been tested with a fake model only.
- **Rate limits.** At the free-tier 30 requests per minute a long skill takes longer because the limiter paces calls. A benchmark of many tasks needs that time budget.
- **Rule checks are narrow.** Only the format kinds above and the begin-with and forbidden-word patterns are enforced; other constraints rely on the verifier.
- **Wording gaps pass.** Contradictions between steps or an invented claim (for example "I have initiated a refund") are not detected.
- `final_output` is the raw last-step text, so it may be wrapped in a code fence. The benchmark scorer strips fences.
- Prompts and checks were tuned on three skills written by the same author. They may not transfer to other skills.
- The cache key ignores `GEMMA_THINKING`, so switch cache folders if you change it.

## 11. Contract notes

- `trace.json` gained one optional field, `totals.cache_hits` (an integer). It is an addition and does not rename or remove anything.
- `compile_skill(skill_text, model=None, source_file="")` fills `source_file` in the plan.
- `run_skill` returns `mock: false`. The `mock` and `harness_is_mock` flags are for stand-ins used elsewhere.
- Step `status` values are exactly `pass`, `repaired`, `fail`.

## 12. Tests

```bash
python -m pytest skillcompiler/tests      # 104 tests, no API key, about 9 seconds
```

A fake model replaces the API in the unit tests. Provider tests use a small local HTTP server. Live runs are manual (sections 6 to 9).

## 13. Adaptive mode, the live stream's limits, and the settings that change behaviour (added 28 Oct)

**Adaptive mode** (`run_skill(..., mode="adaptive")`, `--mode adaptive`, or `SKILLCOMPILER_MODE=adaptive`). The format and rule checks run on every
step in both modes. The model verifier call runs only on *risky* steps: a strict output format (anything but plain text), arithmetic (words such as
add, total, tax, discount, percent, or digits with an operator), a hard rule (at most, at least, exactly, must begin with, never, only), a dependence on
two or more earlier steps, or being the final step. The trace gets the optional field `mode_detail` = `{"strategy": "adaptive", "route": "harness",
"verified_steps": [...], "skipped_verify_steps": [...]}`; full-mode traces are unchanged. `verify=False` or `SKILLCOMPILER_VERIFY=0` turns the verifier off in
both modes, and an explicit argument beats the environment. The step list is the same in both modes, so calls drop by about one per skipped step.

**Why adaptive is worth measuring.** In the official benchmark runs the verifier never rejected a step (0 retries in 76 steps in run 1), yet it
roughly doubled the calls. The format and rule checks, which are not model calls, do the catching. Whether skipping the verifier costs any pass rate is the
question the A4 measurements answer (below).

**Stream limits** (`skillcompiler/stream.py`, `ndjson_events(skill_text, input, verify=, mode=, max_steps=, timeout_s=, ...)`):
- `max_steps`: if the plan has more steps, the plan is sent, then one `error`, and nothing runs.
- `timeout_s`: a whole-run limit. It also fires when one model call hangs: the error is sent at the deadline, and the run stops at its next event.
- The model API failing 3 calls in a row (no quota, an outage, a missing key) stops the run with one error.
- Every failure is exactly one `{"type": "error", "message": ...}` line, then the stream ends; the generator never raises into the web server.
- On disconnect the run stops at its next event and queued events are dropped.
- Optional event fields: `run_start.mode`, `step_end.verified` (whether the model verifier was used for that step).

**Settings that change behaviour** (all default to the behaviour of the official benchmark runs):

| Setting | Default | Effect |
|---|---|---|
| `SKILLCOMPILER_VERIFY` / `--no-verify` | verifier on | `0` removes the verifier call |
| `SKILLCOMPILER_MODE` / `--mode` | `full` | `adaptive` verifies risky steps only |
| `SKILLCOMPILER_COPY_RULE` | `0` | `1` adds the verbatim-copy rule to JSON assembly steps |
| `GEMMA_THINKING` | `MINIMAL` | `default` uses the model's own thinking |
| `GEMMA_RPM`, `GEMMA_TIMEOUT` | 25, 240 | request pacing, per-request time limit |

Any benchmark number should record these settings and the harness commit.

**Auto mode** (`--mode auto`). The skill is linted first (`tools/lint_skill.py`, no model call). A skill of at most 6 steps that the linter rates *low* risk runs
**plain**: the whole skill in one call, a final format check (valid JSON if the skill mentions JSON, otherwise non-empty), and one retry. The trace then has
`mode: "plain"`, no steps, and `mode_detail` = `{"strategy": "auto", "route": "plain", "reason": ..., "final_check": {"ok": ..., "note": ...}}`; a failed
final check is reported there, not hidden. Any other skill, or no linter, runs the harness in adaptive mode (`route: "harness"`). A `route` event is sent either way.
The 6-step and "low" thresholds are starting values, not tuned. **Status: tested with a fake model only**; its pass rate and cost on the frozen tasks are not measured.

**Escalation** (`--escalate-model NAME`). A step that is still failing after its normal retries gets one last attempt, with the same feedback, on the named bigger model
(the verifier call for that attempt also uses it). The attempt carries `"model"`, the step gets `"escalated": true`, and the trace lists `escalated_steps`
(empty if none). A step that passes is never sent up, and escalating to the model already in use does nothing. **Status: tested with a fake model only; no real run yet.**

## 14. Mode comparison on the 10 frozen tasks (28 Oct evening; single runs, API unstable)

Same 10 tasks, `gemma-4-26b-a4b-it`, harness commit `7e778d9`, one run per configuration. Two to three tasks per run had to be filled in with `--resume` after API errors.

| Configuration | Harness | Plain (same run) | Calls/task | Repaired steps | Attempts hit by API errors |
|---|---|---|---|---|---|
| full (verifier on every step) | 7/10 | 7/10 | 16.0 | 4 | 7 of 82 |
| verifier off | 8/10 | 7/10 | 8.7 | 4 | 4 of 81 |
| adaptive (verifier on risky steps) | 6/10 | 7/10 | 15.1 | 0 | 2 of 77 |
| full + copy rule | 9/10 | 7/10 | 16.5 | 3 | 3 of 79 |

**How to read this.** These do not replace the official result (plain 7/10, harness 9/10, identical in three runs). The same default configuration scored 7/10 tonight against 9/10 before, which shows how much a single run moves when the Gemini API returns 500 errors (up to 7 of 82 attempts in one run). Differences of one or two tasks between rows are within that noise. Seconds per task are not comparable between rows (rate limiting and API slowness changed during the evening), so no speed claim is made from them. Calls per task are comparable except for adaptive, whose count includes retries after API errors.

What can be said: the verifier did not obviously help (verifier off was no worse), and adaptive mode did not beat full on these tasks (6/10, with t01 and t06 failing; its call count did not drop here). The copy rule scored best (9/10) but it scored 8/10 in the earlier full re-run, so it stays opt-in. Nothing here is a reason to change a default before the event. Per-task results are in the scratch outputs of the run and are not part of the dataset.

### 14.1 First real-API runs of auto mode and escalation (28 Oct evening)

Single runs on `gemma-4-26b-a4b-it`; they show the paths work against the real API, not that they help.

- **Auto mode** (`--mode auto`): `ticket-triage` (lint 0, low) took the plain route, 1 model call, valid output. `complaint-resolution` (lint 39, medium, 12 steps) took the harness route with 6 steps verified and 6 skipped, 19 calls, 217 s. `meeting-minutes` (lint 12, low, 8 steps) also took the harness route (5 steps verified, 3 skipped), 14 calls, 95 s. So "low lint" does not always mean the plain route: the step count also counts.
- **Escalation** (`--escalate-model gemma-4-31b-it`): tested with a deliberately unsatisfiable step (the plan asks for the capital of France but allows only `alpha` or `beta`). After its retries the step got one last attempt on `gemma-4-31b-it`; that attempt is recorded with `"model": "gemma-4-31b-it"` and the step has `"escalated": true`. The bigger model also failed, as expected. This proves the wiring, not that escalation rescues real failures: no real step has needed it yet.
- `gemma-3-*` models are not available through this API key (404), so a small-to-big escalation with Gemma 3 cannot be demonstrated; `gemma-4-26b-a4b-it` and `gemma-4-31b-it` are.
