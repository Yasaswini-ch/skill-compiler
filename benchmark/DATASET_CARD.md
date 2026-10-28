# Dataset card: Gemma Fail Museum failures

## What it is

A small set of labelled failures of Gemma on long agent skills (`SKILL.md` files), plus the tasks that produced them. Each failure comes from one of two ways of running a task:

- **plain**: the whole skill and the input in one model call, with no help;
- **harness**: the Skill Compiler harness, which splits the skill into steps, runs them one at a time, checks each output and retries.

Files in `benchmark/dataset/`:

| File | Content |
|---|---|
| `tasks.jsonl` | The 10 tasks used, one per line, with the full skill text embedded. |
| `failures.jsonl` | The failures of the official run (run 1), one per line. |

A failure line has: `failure_id`, `task_id`, `task_title`, `difficulty_tags`, `mode`, `label`, `what_went_wrong` (the real failed checks), `failed_checks`, `output_excerpt` (first 300 characters), `label_note` and `scorer_label` (when a person changed the label), and the run settings (`run`, `model`, `verifier`, `gemma_thinking`, `tasks_sha256`).

## How it was made

- **Tasks:** 10 hand-written tasks over 6 original skills (`skills/`). Each task has 4 to 7 checks that a script can verify (`scorer.py`, no model calls). Difficulty types: similar-sounding steps, strict output format, step order, hard limits.
- **Frozen:** `tasks.json` was frozen before the first plain run (SHA-256 `53351f62f15b026cb6c653e43c591c60ce1b4877ba9f3522b1c6fba1f427bfd2`, see `FROZEN.md`). One check (t06, eggs row) was fixed after the baseline was seen, because it was over-strict; the fix applies equally to plain and harness. The details and both hashes are in `FROZEN.md`.
- **Model and settings:** `gemma-4-26b-a4b-it` through the Gemini API, harness verifier ON, `GEMMA_THINKING` unset (default `MINIMAL`), no cache, 25 requests per minute.
- **Runs:** 3 runs with identical settings. Run 1 is the official run and the source of `failures.jsonl`. Runs 2 and 3 are repeats for variance (see `RESULTS_NOTE.md`); their failures are not in the dataset.
- **Official result (run 1):** plain 7 of 10 passed, harness 9 of 10. This is a small sample and one run per setting.
- **Failures in the dataset:** 4 (3 plain: t04, t05, t08; 1 harness: t03).
- **Labels:** the scorer gives each failure the label written on the first failed check. A person then reviewed every failure (`label_overrides.json`) and changed 3 of the 4 labels: t03 harness from `lost_track` to `wrong_format`, and t04 and t05 plain from `lost_track` to `other`. The t08 plain label stayed `wrong_format`; it is listed in the overrides with a reason. The scorer's own label is kept as `scorer_label` where it differs.

## Labels

7 labels: `skipped_step`, `wrong_format`, `lost_track`, `merged_steps`, `hallucinated_step`, `ignored_constraint`, `other`. Definitions and the real examples are in `FAILURE_LABELS.md`.

Counts in this dataset: `wrong_format` 2, `other` 2, and 0 for each of the other five labels.

## Generated tasks (Phase 2, not done yet)

| | Count |
|---|---|
| Hand-written tasks used | 10 |
| Generated tasks | [PLACEHOLDER] |
| Generated tasks dropped by schema validation | [PLACEHOLDER] |
| Generated tasks hand-checked | [PLACEHOLDER] |
| Generated tasks dropped after hand-check | [PLACEHOLDER] |

Generated results, if any, are kept separate from the official results and are not in `failures.jsonl`.

## Known limits

- Small: 10 tasks, 4 failures, one model, one setting.
- The failures come from one run. Gemma's output varies; in runs 2 and 3 the same tasks failed, but plain's wrong numbers were different each time.
- The checks are programmatic and keyword based. A wrong check would create a fake failure, and a wrong but plausible answer can pass.
- Labels were reviewed by one person. Arithmetic errors have no label of their own and are filed under `other`. Five of the seven labels have no real example yet.
- `output_excerpt` is cut at 300 characters.
- The harness never needed a retry in run 1, so these harness failures say nothing about the retry mechanism.

## License

The repository is under the MIT License (`LICENSE`), and this dataset is distributed under the same license. The model outputs in it were produced by Gemma; [PLACEHOLDER: confirm Gemma's terms for redistributing model outputs]. Owner must verify Google's terms before publishing.
