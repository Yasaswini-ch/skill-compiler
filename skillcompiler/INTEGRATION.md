# Integration notes for Sriya (benchmark) and Likhitha (web)

Harness status: finished and on `main`. After `git pull --rebase origin main` you have everything.
Quickstart: [`README.md`](README.md). Full notes: [`../docs/HARNESS.md`](../docs/HARNESS.md).
Questions or harness bugs: message Yasaswini with the `trace.json` and the command you ran.

## What you can call

```python
from skillcompiler import run_skill, compile_skill
trace = run_skill(skill_text, user_input)      # trace.json dict, mode "harness", mock false
plan  = compile_skill(skill_text)              # plan.json dict
```

CLI: `python -m skillcompiler run SKILL.md --input-file in.txt --trace trace.json`

Contract: unchanged except one optional extra field, `trace.totals.cache_hits` (integer). Readers must not require it:
an older sample trace does not have it.

## Rate limit (read this)

The free Gemini tier allows **30 requests per minute per model, per project** (each of you has your own key). A skill run makes about
`2 x steps + 1` calls (a 12-step skill is about 25), so the harness paces itself at 25 requests per minute and, on a 429, waits for the
server's "retry in Ns" hint. Long runs are therefore slower, not broken. `GEMMA_RPM=0` removes the pacing. Run in the background, not in a demo.

## Open decision: verifier on or off

By default every step costs two calls: the answer and a model "verifier" that says PASS or FAIL. Setting `SKILLCOMPILER_VERIFY=0` (or `--no-verify`)
keeps the format and wording-rule checks but skips the verifier call.

On 5 informal stress tasks, one run each, both modes passed all 5 checks; the verifier-off run used 30 calls instead of 63 and took about
118 s instead of 185 s. That says nothing about wrong-but-well-formed answers, which only the verifier can catch.
**Whichever mode the final benchmark uses, write it next to the numbers** (README, results page, dataset card).
Suggested default for the official run: verifier on. Use verifier-off for quick test runs.

## Sriya (benchmark)

- Your adapter can use the real harness now: `try: from skillcompiler import run_skill`. Do not keep `harness_is_mock: true` once the import works.
- `run_skill` never raises on a bad step: failures are recorded in the trace (`status: "fail"`). Only a missing key or model raises.
- `final_output` may be wrapped in a code fence. Strip fences in the scorer, as planned.
- Time budget: 10 tasks x (about 15 to 25 calls) at 25 requests per minute is roughly 10 to 20 minutes for the harness alone. Start early, use `--resume`.
- To avoid paying twice while debugging, run the harness with `--cache` (CLI) or call `skillcompiler.cache.configure(True)`;
  a repeated identical prompt is then free. Do not use a cache for the final measured run unless you say so in the report.
- Env: your own `GEMINI_API_KEY` and `GEMMA_MODEL=gemma-4-26b-a4b-it` (this key can use `gemma-4-26b-a4b-it` and `gemma-4-31b-it`; the 31b was slower and returned server errors in testing).
  Gemma "thinking" is set to MINIMAL by default for speed. If you compare plain Gemma with the harness, set the same `GEMMA_THINKING` for both
  (`GEMMA_THINKING=default` uses the model's own setting), or say which you used.

## Likhitha (web)

- Real traces to build the viewer against: [`examples/traces/`](examples/traces/README.md). One has `pass`, `repaired` and `fail` steps together.
- Live mode: call `run_skill` in a worker thread if you like: run counters are per thread, so a harness and a plain run side by side do not mix their totals.
  Expect 30 to 90 s per harness run; show progress and keep the "Use recorded demo" button.
- Offline demo: run the exact demo inputs once with `--cache`, keep `.skillcompiler_cache/`, then rehearse with `--replay` (0 API calls, works without internet).
  Any change to a skill, input or prompt needs a fresh cached run. The cache folder is not git-ignored yet: add it to `.gitignore` or commit it on purpose.
- The `--replay` mode stops with a clear error on a cache miss rather than calling the API, which is what you want on stage.
- `docs/HARNESS.md` is a new file in `docs/`; nothing of yours was changed.
