# Sample traces (real runs)

Real `trace.json` files from the harness, for building and testing viewers. All have `"mock": false`.
Each is a single run on 24 Oct 2026, so they show the format and are not benchmark results.

| File | Model | Shows |
|---|---|---|
| `ticket-triage_gemma-4-26b_one-repair.json` | gemma-4-26b-a4b-it | 6 steps. Step 2 failed its format check, got feedback, then passed (`repaired`). Made before `totals.cache_hits` existed, so that optional field is missing: viewers must cope. |
| `ticket-triage_gemma3-4b_pass-repaired-fail.json` | gemma3:4b (local Ollama) | All three statuses: `pass`, `repaired` (step 3) and `fail` (steps 2 and 4, three attempts each). 22 calls, 502 s. |
| `complaint-resolution_gemma-4-26b_12-steps-all-pass.json` | gemma-4-26b-a4b-it | 12 steps, no retries. 25 calls, 70 s. |

`final_output` may be wrapped in a ```json fence, and `checker_note` can be long. Shape: `contract/trace.json`.
