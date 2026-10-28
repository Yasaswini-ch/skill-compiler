# Unfinished work (as of 29 Oct)

Hack Day is Sun 1 Nov. Features freeze Fri night. Tag `v1.0` after the 3 PM freeze on Sunday. Submit by 3:45 PM.
This lists only what is NOT done. What is done is on `main`.

## Done already (do not redo)

- Harness: modes (`full`, `adaptive`, `auto`), escalation, event stream, hardened errors, request timeout. Auto mode and escalation have had first real-API runs (`docs/HARNESS.md` section 14.1).
- Mode comparison on the 10 frozen tasks, with API-error counts and caveats (`docs/HARNESS.md` section 14).
- Web: X-ray, Break Gemma Arena, Skill Doctor, proof report download, real data in `web/data/`.
- Docs: demo script v2, `docs/ARENA_OPERATOR.md`, README sections.
- Benchmark side (merged in PR #13): experiment table (`benchmark/experiment_results.json`), 4 tested arena presets (`benchmark/attack_presets.json`), local-model support in `run_compare`, dataset card licence corrected to Gemma 4 = Apache 2.0.
- Team messages sent.

## Still open

1. **Local-model run.** `run_compare` now supports a local provider, but no local-model results exist yet (`experiment_results.json` has only the two Gemini rows). Run the 10 tasks, plain and harness, with a small local Gemma (for example `gemma4:e2b` through Ollama) into a NEW output folder, never `benchmark/output/`. Check `python -m benchmark.run_compare --help` for the flags. Report pass counts and the model name. This is the fallback if the API is down at the event.
2. **After the event:** read `web/arena_log.jsonl` by hand (it holds attendee text; never commit it) before adding any confirmed failures to the dataset.
3. **Friday integration and freeze; Sunday tag `v1.0`; git identity.**
4. **Backup demo video** (2 minutes; shot list in `docs/DEMO_SCRIPT.md`).
5. **C6, the Chrome extension** (stretch goal, not started; skip if time is short).
6. Optional: decide after more runs whether adaptive mode or the copy rule should ever become a default. Tonight's numbers say no.

## Everyone, before Friday night

- [ ] No MOCK banner on any page used in the demo.
- [ ] Two timed dry runs of the 3-minute demo.
- [ ] Arena practice attempt works; API key and rate limit checked.
- [ ] Phone hotspot, chargers, recorded demo loads offline.

## Honest caveats to keep in mind

- Official result: plain 7/10, harness 9/10 on 10 tasks, about 16 times the calls. The 28 Oct evening single runs scored lower (harness 6 to 9 of 10) because the Gemini API returned many 500 errors. Do not quote them as the headline.
- Free tier is about 30 requests per minute per model; one arena attempt uses roughly 15 calls.
