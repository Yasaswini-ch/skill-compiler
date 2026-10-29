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

## Generated tasks

Gemma was asked to write 3 harder variants of each hand-written task (`gen_variants.py`). The generated tasks are a separate, supplementary set: they are not in `tasks.jsonl` or `failures.jsonl`, and their results are not part of the official 7 of 10 vs 9 of 10.

| | Count |
|---|---|
| Hand-written tasks used (official) | 10 |
| Generated variants requested | 30 |
| Dropped at schema validation | 5 (t02 x 3: invalid check label; t04 x 1 and t07 x 1: invalid difficulty tag) |
| Valid generated tasks | 25 |
| Hand-reviewed (random sample, seed 1) | 12 |
| Dropped after hand-check | 5 (t04-v2, t04-v3, t03-v1, t03-v2, t09-v1) |
| Kept and used | 7 |
| Unreviewed, excluded | 13 |

5 of the 12 hand-reviewed generated tasks (42%) had broken or ambiguous checks, so the 13 unreviewed tasks are not used anywhere.

Two checks of kept tasks were edited after review, and nothing else (details and hashes in `GENERATED_REVIEW.md`):

- **t05-v1**, checks c4 to c7: the literal quote characters were removed from the regexes, because they could never match the unquoted field value.
- **t08-v3**, check c5: the scale factor line now accepts `10` or `10.0`.

The 7 kept tasks (`tasks_generated_reviewed.json`, SHA-256 `3b0d781b…`) were run once, plain against harness, with the same settings as the official run: plain 5 of 7, harness 6 of 7, 3 failures. Results are in `output/generated/` (see its `README.md`).

## Known limits

- Small: 10 tasks, 4 failures, one model, one setting.
- The failures come from one run. Gemma's output varies; in runs 2 and 3 the same tasks failed, but plain's wrong numbers were different each time.
- The checks are programmatic and keyword based. A wrong check would create a fake failure, and a wrong but plausible answer can pass.
- Labels were reviewed by one person. Arithmetic errors have no label of their own and are filed under `other`. Five of the seven labels have no real example yet.
- `output_excerpt` is cut at 300 characters.
- The harness never needed a retry in run 1, so these harness failures say nothing about the retry mechanism.
- The verifier can demand things a step did not ask for: in the generated run, t01-v2 step 4 ("Extract OS") was retried because the verifier asked for the app version in the OS value.

## License

The repository is under the MIT License (`LICENSE`), and this dataset is distributed under the same license. The model outputs in it were produced by Gemma (`gemma-4-26b-a4b-it`) through the Gemini API's free tier.

**Terms checked on 28 Oct 2026** (read from ai.google.dev, gemma.ai and Hugging Face; this is not legal advice):

- *Gemma 4 license.* The model used, `gemma-4-26b-a4b-it` (Hugging Face: `google/gemma-4-26B-A4B-it`), carries the **Apache License 2.0** (license tag `apache-2.0` on its Hugging Face page; the Gemma site lists the "Gemma 4 license" and its text is the Apache License 2.0). The Apache License 2.0 has no clause about model outputs. The Gemma site does not say in words which models the "Gemma 4 license" page covers; the model page's license tag and the site menu are what say so.
- The older *Gemma Terms of Use* (section 3.3 on outputs, section 1.1(e) "Model Derivatives") do **not** govern this model: they state that they apply to the Gemma models listed in their Appendix, which does not list Gemma 4, and they say "For Gemma 4 terms, see the Gemma 4 license". They are mentioned only so that nobody applies them here by mistake.
- The *Gemma Prohibited Use Policy* is written for "Gemma or Model Derivatives" without naming versions, and the pages read do not say whether it applies to Gemma 4. We follow its intent anyway: anything from the arena is reviewed by a person before export.
- The *Gemini API Additional Terms* (the service the model was called through): on the unpaid tier Google may use submitted prompts and generated responses to improve its products, and human reviewers may read them; do not submit sensitive, confidential or personal information. Google does not claim ownership of generated content, and the user is responsible for how it is used and shared. The service may not be used to develop models that compete with it. This dataset makes no claim about training any model.

Sources: https://huggingface.co/google/gemma-4-26B-A4B-it, https://ai.google.dev/gemma/apache_2, https://ai.google.dev/gemma/terms, https://ai.google.dev/gemma/prohibited_use_policy, https://ai.google.dev/gemini-api/terms (the Gemma documentation pages say they are deprecated and point to https://gemma.ai). The repository owner should read these pages once more before publishing, because terms can change.
