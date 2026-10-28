# Running the Break Gemma Arena

For whoever sits at the arena laptop. The arena is `web/arena.html`; its server side is `web/arena.py`, started by `python web/server.py`.

## What it does

People try to make plain Gemma fail while the harness runs beside it.

- **Challenge**: a tested preset. `benchmark/scorer.py` scores both answers with the preset's checks. Only a challenge where plain failed adds to the "failures collected" counter.
- **Free play**: any instructions. Both outputs are shown and marked UNVERIFIED. Nothing is scored or counted.
- Mock presets and stand-in model runs are never counted.

## Before the event

1. `.env` has `GEMINI_API_KEY` and `GEMMA_MODEL`. Start `python web/server.py` and open `http://127.0.0.1:5000/arena.html`.
2. Run one practice challenge. Check the page does not say MOCK or STAND-IN.
3. Free tier is about 30 requests per minute per model. One attempt uses roughly 15 calls in adaptive mode, so expect about two attempts a minute at best. The queue is first-in first-out, one run at a time.

## Settings (environment variables)

| Variable | Default | Meaning |
|---|---|---|
| `ARENA_MODE` | `adaptive` | Harness mode for arena runs (`full`, `adaptive`, `auto`). |
| `ARENA_PROVIDER` | `gemini` | `local` uses an OpenAI-compatible server (for example Ollama). |
| `ARENA_BASE_URL` | `http://localhost:11434/v1` | Where the local server is. |
| `ARENA_MODEL` | none | Local model name. The page then shows LOCAL MODEL (name). |
| `ARENA_PRESETS` | built in | Path to a custom presets file. |
| `ARENA_LOG`, `ARENA_TRACES` | `web/arena_log.jsonl`, `web/arena_traces/` | Where attempts are saved. |

## Fallbacks

- **API errors or rate limits**: the attempt shows the error. Wait a minute, or switch to the local model (`ARENA_PROVIDER=local ARENA_MODEL=<name>`). A local run is labelled; do not mix its failures with Gemma's in what you say.
- **Nothing works**: use the X-ray replay and say it is a recording.
- **Stuck queue**: an attempt whose page closes is dropped; a joined attempt that never opens its stream is dropped after 25 seconds.

## Privacy rules (say these out loud if asked)

- Only a nickname and the text people type are saved. No names, emails or IP addresses.
- People must tick the consent box before joining.
- `arena_log.jsonl` and `arena_traces/` hold attendee text. They are gitignored and the web server refuses to serve them. **Never commit them or put them in the dataset without checking the text first.**
- Limits: input 1500 characters, skill 6000 characters and at most 6 steps, 5 attempts per nickname.

## After the event

Read `web/arena_log.jsonl`, remove anything personal, and only then consider adding confirmed failures to the dataset (through Sriya's `benchmark/` process).
