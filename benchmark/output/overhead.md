# Overhead: plain vs harness

Measured on the 10 frozen tasks, one run. Every number comes from `results.json`.

| Setting | Value |
|---|---|
| Model | `gemma-4-26b-a4b-it` |
| GEMMA_THINKING | unset (default MINIMAL) |
| Verifier | ON |
| Cache | OFF |
| Harness is mock | no |
| tasks.json SHA-256 | `53351f62` (`53351f62f15b026cb6c653e43c591c60ce1b4877ba9f3522b1c6fba1f427bfd2`) |
| Run time | 2026-10-28T12:30:22+05:30 |

## Per task

| Task | Plain calls | Harness calls | Calls ratio | Plain latency (s) | Harness latency (s) | Latency ratio | Plain | Harness |
|---|---|---|---|---|---|---|---|---|
| t01 | 1 | 18 | 18.0x | 5.3 | 93.8 | 17.8x | PASS | PASS |
| t02 | 1 | 16 | 16.0x | 4.5 | 66.2 | 14.7x | PASS | PASS |
| t03 | 1 | 17 | 17.0x | 3.4 | 48.9 | 14.5x | PASS | FAIL |
| t04 | 1 | 19 | 19.0x | 3.2 | 46.2 | 14.6x | FAIL | PASS |
| t05 | 1 | 19 | 19.0x | 3.1 | 48.5 | 15.5x | FAIL | PASS |
| t06 | 1 | 13 | 13.0x | 3.1 | 33.0 | 10.8x | PASS | PASS |
| t07 | 1 | 13 | 13.0x | 2.2 | 31.2 | 13.9x | PASS | PASS |
| t08 | 1 | 13 | 13.0x | 3.3 | 33.6 | 10.1x | FAIL | PASS |
| t09 | 1 | 17 | 17.0x | 3.7 | 55.7 | 14.9x | PASS | PASS |
| t10 | 1 | 17 | 17.0x | 3.9 | 42.0 | 10.8x | PASS | PASS |

## Totals and averages

| | Plain | Harness | Ratio |
|---|---|---|---|
| Calls, total | 10 | 162 | 16.2x |
| Calls, per task | 1.0 | 16.2 | 16.2x |
| Latency, total (s) | 36 | 499 | 14.0x |
| Latency, per task (s) | 3.6 | 49.9 | 14.0x |

Latency is the sum of the model calls' time as recorded in each trace; it does not include the 2 s pause between runs or the rate limiter's waits.
