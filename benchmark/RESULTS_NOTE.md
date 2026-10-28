# Results note

## Facts

- 10 frozen tasks (`tasks.json`, SHA-256 `53351f62…`, see `FROZEN.md`), one run. This run (`output/results.json`) is the official one.
- Plain Gemma: **7 / 10** passed. It failed t04, t05 and t08.
- Harness: **9 / 10** passed. It failed t03: the output had `"meets_minimum": false` (a boolean) instead of the required string `"no"`. Label: `wrong_format`.
- 0 retries and 0 repaired steps in 76 steps. Every harness step passed on its first attempt.
- The harness cost about 16x the calls (16.2 per task against 1.0) and about 14x the latency (49.9 s per task against 3.6 s). Details: `output/overhead.md`.
- The t06 check was fixed after the baseline was seen (see `FROZEN.md`). The check was over-strict, and the fix applies equally to plain and harness.

## Settings

| | |
|---|---|
| Model | `gemma-4-26b-a4b-it` |
| GEMMA_THINKING | unset (default MINIMAL) |
| Verifier | ON |
| Cache | OFF |
| Harness | real (`harness_is_mock: false`) |

## Limitations

- Small sample: 10 tasks.
- One run. Gemma's output varies from run to run, so another run could give different pass counts.
- The harness gained only on arithmetic and fixed-table tasks (t04, t05, t08). It lost t03, which plain passed.
- The retry mechanism was not exercised: no step needed a retry.
- The semantic checks are keyword-based, so a wrong but plausible answer can pass them.

## Repeat runs (variance)

Run 1 is the official result (`output/results.json`). Runs 2 and 3 are repeat runs with identical settings (same model, verifier ON, no cache, GEMMA_THINKING unset, tasks hash `53351f62`), saved in `output/run2/` and `output/run3/`. All three runs are reported; none was dropped or re-run to get a better result.

| | Run 1 (official) | Run 2 | Run 3 |
|---|---|---|---|
| Plain passed | 7 / 10 | 7 / 10 | 7 / 10 |
| Harness passed | 9 / 10 | 9 / 10 | 9 / 10 |
| Plain failed | t04, t05, t08 | t04, t05, t08 | t04, t05, t08 |
| Harness failed | t03 | t03 | t03 |
| Calls, plain / harness | 10 / 162 (16.2x) | 10 / 165 (16.5x) | 10 / 166 (16.6x) |
| Latency, plain / harness | 36 s / 499 s (14.0x) | 58 s / 440 s (7.6x) | 37 s / 602 s (16.3x) |
| Harness steps | 76 | 77 | 76 |
| Repaired steps / retries | 0 / 0 | 0 / 0 | 1 / 2 |

Every task had the same pass or fail result in all three runs.

- **t03 (harness) failed the same way in every run:** `"meets_minimum": false` (a boolean) instead of the string `"no"`. In run 3 the `skills` field was also a JSON array instead of a comma-separated string (check c6 failed as well).
- **Plain failed the same three tasks every time, with different wrong numbers each run.** For example the t04 subtotal was 157.75, 157.75 and 155.75 (correct: 150.75).
- **Run 2 was interrupted.** The process hung on t04 with no error in the log. Run 2 was resumed with `--resume`: t01-t03 are from the first attempt (including the recorded t03 failure) and t04-t10 from the resumed attempt.
- **Run 3 had the only repaired step:** t04, step 6 ("Calculate Discount"). The model returned an empty output twice; the third attempt (`0.00`) was accepted. That is 3 attempts and 2 retries. The log shows an SDK warning `MALFORMED_RESPONSE is not a valid FinishReason` around t04; the cause was not verified. The retry mechanism has therefore run once, on an empty output and not on a wrong answer.
- **Latency varies much more than calls.** Calls were 16.2x to 16.6x. The latency ratio ranged from 7.6x to 16.3x, and run 3's t03 took 187 s against 41 to 49 s in the other runs.
- **Step counts differ slightly** because the splitter is not deterministic: in run 2 it produced 7 steps for t07 instead of 6.
- **Run 1's `tasks_sha256` was filled in afterwards.** It was added to `results.json` after the run, once the hash of `tasks.json` had been checked before and after that run. Runs 2 and 3 recorded it themselves.
