# Local model run: PARTIAL, not a result

Model `gemma4:e2b` through Ollama (provider `openai-compatible`, port 11500), the 10 frozen tasks, plain and harness, verifier on.

**Only t01 finished (1 of 10 tasks): plain PASS, harness PASS.** The run was interrupted when the session ended, so `results.json` here covers one task and its "1/1" must not be quoted as a pass rate. It will be completed with `--resume` and this note replaced.

This is a supplementary fallback run, never the headline. The official result is plain 7/10, harness 9/10 (`benchmark/output/`).
