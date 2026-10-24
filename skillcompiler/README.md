# skillcompiler (the harness)

Splits a SKILL.md into steps, runs them one at a time on a small model, checks every output, and retries with feedback.

1. `pip install google-genai python-dotenv pytest pyyaml`
2. Copy `.env.example` to `.env` (repo root) and set `GEMINI_API_KEY` and `GEMMA_MODEL`.
3. Split: `python -m skillcompiler compile skillcompiler/examples/ticket-triage/SKILL.md -o plan.json`
4. Run: `python -m skillcompiler run skillcompiler/examples/ticket-triage/SKILL.md --input-file skillcompiler/examples/ticket-triage/input.txt --trace trace.json`
5. From Python: `from skillcompiler import run_skill, compile_skill`
6. Flags: `--model`, `--max-retries N`, `--no-verify` (format check only).
7. Tests (no API key needed): `python -m pytest skillcompiler/tests`
8. Compile once, run many: `compile ... -o plan.yaml` (or .json), then `run ... --plan plan.yaml`.
9. Cache: `--cache` saves responses in `.skillcompiler_cache/`; `--replay` uses only the cache (0 API calls, works offline).
10. Set `GEMMA_THINKING=default` to use the model's own thinking (slower).
