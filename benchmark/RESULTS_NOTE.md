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
