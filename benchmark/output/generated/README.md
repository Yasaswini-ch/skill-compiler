# Generated tasks: supplementary result

**This is a supplementary result. It is NOT part of the official result (plain 7/10 vs harness 9/10, in `../results.json`).** The numbers must not be mixed.

## What was run

- 7 hand-checked generated tasks from `benchmark/tasks_generated_reviewed.json` (SHA-256 `3b0d781b32ac77a3c32f34d7bac6397e5c5d78b98a2bf431a016c90bb7da7e5b`, see `benchmark/GENERATED_REVIEW.md`).
- One run, plain Gemma against the harness on each task.
- Model `gemma-4-26b-a4b-it`, verifier ON, `GEMMA_THINKING` unset (default MINIMAL), no cache, 25 requests per minute.
- Run finished 2026-10-28 17:26 +0530.

## Which generated tasks were checked

- 25 generated tasks were valid. 12 of them were reviewed by hand, and 5 of those 12 had broken or ambiguous checks.
- 13 tasks were not reviewed. They are excluded and are not in this run.
- 7 tasks were kept and used (the 12 reviewed minus the 5 dropped).

## Results

| | Plain | Harness |
|---|---|---|
| Passed | 5 of 7 | 6 of 7 |
| Model calls | 7 | 112 (16.0x) |
| Latency, total | 40 s | 825 s (20.8x) |

Harness latency was very uneven: three tasks took about 205 to 219 s (t01-v2, t01-v3, t05-v1), and the other four took 33 to 69 s.

| Task | Plain | Harness |
|---|---|---|
| t01-v2 | PASS | FAIL |
| t01-v3 | PASS | PASS |
| t05-v1 | FAIL | PASS |
| t06-v2 | PASS | PASS |
| t07-v2 | FAIL | PASS |
| t07-v3 | PASS | PASS |
| t08-v3 | PASS | PASS |

## Failures (3, in `failures.json`)

- **t01-v2, harness (`wrong_format`):** the version was written `5.5.0` instead of `v5.5.0`.
- **t05-v1, plain (`other`):** arithmetic error, wrong subtotal (441.50 instead of 441.60), later numbers follow it.
- **t07-v2, plain (`other`):** arithmetic error, free minutes 190 instead of 200.

The labels of the two plain failures were changed by hand from the scorer's `lost_track` to `other` (`label_overrides.json` in this folder; the scorer's own label is kept as `scorer_label` in `results.json`).

## Retries and repaired steps

One repaired step, in t01-v2, step 4 ("Extract OS"). The model answered `Android 14`; the verifier asked for the app version (5.5.0) to be included in the OS value, which the step did not ask for (it asks for the operating system including its own version number). The retry answered `Android 14 (version 5.5.0)`, which arguably made the answer worse. The final `os` field in the JSON was `Android 14`. All other harness steps passed on their first attempt.

## Files

`results.json`, `failures.json` (labels as above), `traces/` (one trace per task and mode), `label_overrides.json`, `dropped_variants.json` and `review_sample_seed1.txt` (from the generation and review steps).
