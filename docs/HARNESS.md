# Harness notes (`skillcompiler/`)

Design, usage and findings for the harness, written by the harness owner (Person A).
The one-page quickstart lives in [`skillcompiler/README.md`](../skillcompiler/README.md).

> Every number in this file comes from a real run on the date it was measured
> (24 Oct 2026, model `gemma-4-26b-a4b-it` unless stated) and is a **single run**.
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
| `--cache` / `--replay` / `--cache-dir DIR` | both | See section 6. |
| `--provider`, `--base-url URL` | both | See section 7. |

Progress lines go to stderr, so `stdout` can be piped. A missing file, missing `.env` or bad plan prints a short `error:` line and exits with code 1.

Environment (`.env` in the repo root, never committed): `GEMINI_API_KEY`, `GEMMA_MODEL`,
optional `GEMMA_THINKING`, `GEMMA_RPM` (section 8) and `SKILLCOMPILER_VERIFY=0` (turns the verifier call off for every run; an explicit `verify=` argument or `--no-verify` still wins), `OPENAI_API_KEY` and `OPENAI_BASE_URL` for the other provider.

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
| **Thinking made calls very slow.** Gemma 4 spends hidden "thinking" tokens. | A splitter call on `gemma-4-26b-a4b-it` used 6,770 thinking tokens for 678 answer tokens and took 158 s. Short prompts took 3 to 5 s. | `llm.py` sends `thinking_level="MINIMAL"` by default: the same call took 14 to 19 s. `thinking_budget` and `LOW` are rejected by this model. `GEMMA_THINKING=default` restores the model's own setting. Effect on answer quality is not measured. |
| `gemma-4-31b-it` was no better. | 104 s on the same prompt, and 3 of 6 calls returned HTTP 500. | Stayed on the 26b model. |
| **The model copied the format label.** | For `one_of:shipping|quality|billing|other` it answered `one_of:quality`, twice. | The prompt now describes the format in words ("exactly one of these values and nothing else: ..."). |
| **The verifier was too strict and too wordy.** | It rejected `shipping` where `quality` was equally arguable, and its rambling reason became the retry feedback. | Verifier prompt: fail only clear violations, pass if several answers are reasonable, 25 words. Reasons are cut to 200 characters. |
| **A begin-with rule was missed.** | `Internal note:` prefix dropped and the verifier passed it. | `check_constraints()` enforces begin-with and forbidden-word rules without a model call. |
| **A correct answer was rejected.** | The skill asked for comma-separated names; the `list` check wanted one per line. | `list` accepts comma-separated items; the prompt hint no longer dictates a layout. |
| **Free-tier rate limit.** The API allows **30 requests per minute per model**; a 12-step skill makes about 25 calls, and back-to-back runs exceeded the limit (HTTP 429, "retry in 48s"). | A 429 mid-run made the verifier unavailable for one step. | `llm.py` has a sliding-window limiter (default 25 requests per minute, `GEMMA_RPM=0` turns it off) and, on a 429, waits for the server's own "retry in Ns" hint (cap 70 s). Applies to the `gemini` provider only. |
| **The verifier made a correct answer worse.** | On `2 x 3.50 + 4 x 1.25 + 8.00` the model answered `20.00` (correct); the verifier rejected it twice with wrong arithmetic, the model switched to `19.00`, and that was accepted. In another task it flip-flopped on an ambiguous label (`travel`, `other`, `travel`). | If the model gives an answer it already gave earlier in the same step and only the verifier objects, the answer is kept (step status `repaired`, note `model repeated its answer; verifier objection overruled`). A format or rule failure is never overruled. |
| **A rule for the final answer did not reach the last step.** | Skill said the text must begin with "Meet the"; the final text began "Meet this" and every step passed. | The splitter prompt now says to repeat rules that apply to the final answer in the last step's instruction. This relies on the model following it. |
| **Run counters were global.** | Two runs at once (live mode, a web server) would have mixed their `totals`. | `llm.stats` is now kept per thread. |
| The splitter sometimes adds small wording. | One plan added "Use the rating and reason from step 3" to the final step. | Not changed. The plan can be saved and edited (`compile -o`, then `--plan`). |

## 9. Live runs of the examples (single runs, after all the changes above)

| Skill | Steps | Result | Retries | Calls | Time |
|---|---|---|---|---|---|
| `ticket-triage` | 6 | 6 pass | 0 | 12 | 31 s |
| `meeting-minutes` | 8 | 8 pass | 0 | 15 | 48 s |
| `complaint-resolution` | 12 | 11 pass, 1 repaired (sentiment) | 1 | 25 | 90 s |

Calls per run are about 2 per step (one answer, one verification) plus one for the split, so a run costs
roughly `2N + 1` calls. Runs are not deterministic: an earlier run of `ticket-triage` repaired its classify step.

**Stress test (informal, 24 Oct, one run each, not part of the repo).** Five tasks written to resemble the benchmark's difficulty types
(similar-sounding steps with strict JSON, a fixed table, step order, hard word and wording limits, a skill with headings and no numbers),
each checked by a short script and run through the harness and as one plain call.
After the fixes above the harness passed all 5 and plain Gemma passed 3 (it failed the table total and the step-order arithmetic).
The checks were written by the harness author and the sample is five runs, so this shows the harness behaves sensibly on varied skills
and does not show how much it helps. That measurement belongs to `benchmark/`. Before the fixes the same test exposed the rate-limit,
verifier and final-rule problems in section 8, and the harness did not crash on any task.

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
