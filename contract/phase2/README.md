# Phase 2 contract (shared files)

Phase 1 files in `contract/` (plan, trace, results, failures) are unchanged. These are the new shared shapes.
Everything here is **mock**: the files carry `"mock": true` (or are labelled) so no page may show them as results.
Change a shape only by agreement of all three; prefer adding optional fields. Current version: see `VERSION`.

| File | Written by | Read by | Meaning |
|---|---|---|---|
| `experiment_results.json` | B | C | Model comparison table (plain / harness / adaptive per model) |
| `attack_presets.json` | B | C | Tested challenges for the arena |
| `arena_log.jsonl` | C | B | Every arena attempt, one JSON object per line |
| `events_sample.ndjson` | A | C | Example of the live event stream (also what `skillcompiler/stream.py` sends) |
| `mode_detail.json` | A | C | Optional `trace.mode_detail`: which steps were verified in adaptive mode |

Each shape has a JSON Schema (`*.schema.json`). `skillcompiler/tests/test_contract_phase2.py` checks every mock file against its schema
(it needs the `jsonschema` package and is skipped without it).

## Event stream

One JSON object per line. Types: `run_start`, `plan`, `step_start`, `attempt_start`, `attempt_end`, `step_end`, `run_end` (carries the full trace),
and `error` (`{"type": "error", "message": "..."}`, always the last line). Optional fields may be added; readers must ignore unknown fields.
`events_sample.ndjson` is a two-step run with one repaired step (mock). Real events come from `run_skill(..., on_event=...)`.

## Rules that go with these files

- Numbers come from saved runs only. Frozen tasks stay frozen (`benchmark/FROZEN.md`).
- `arena_log.jsonl` and `web/arena_traces/` hold attendee text: they are never committed.
- Free-play arena rows have `passed: null` and `broke_plain: null` and are never counted as failures.
- **Arena privacy notice must be accurate.** Attendee text is sent to Google's Gemini API on the free tier, where Google may use prompts and
  responses to improve its products and human reviewers may read them (Gemini API Additional Terms, checked 28 Oct 2026). The consent box must say
  so, and must tell people not to type personal data. "May be added to a public dataset after review" alone is not enough.
- Publishing model outputs: see the terms summary in `benchmark/DATASET_CARD.md`.
