# Demo script (3 minutes)

Roles: **Speaker** talks. **Operator** (Yasaswini) runs the arena and live mode. **Number-answerer** (Sriya) takes questions about results and method.
Before going on: `python web/server.py` running, tabs ready for `museum.html`, `xray.html`, `index.html`, `arena.html`, `doctor.html`. Real data in `web/data/`, no MOCK banner visible on any page you use.

| Time | What happens | Say |
|---|---|---|
| 0:00 | Problem | "Small models skip steps when you give them a long list of instructions, and they do it silently." |
| 0:20 | **Fail Museum** (`museum.html`): open two real failures from plain Gemma | "Here plain Gemma added up an invoice wrongly: the subtotal and the tax did not match (task t04, failure f002). Here it got one row of a scaled recipe table wrong (task t08, failure f004). These are real outputs, labelled and in a public dataset." |
| 1:00 | **X-ray** (`xray.html`): replay the one-repair run | "The harness gives one step at a time. This step failed its check, got the checker's note, tried again and passed. The page says REPLAY because it is a recording." Press **Download report** to show the one-file proof report. |
| 1:40 | **Score page** (`index.html`) | "On 10 tasks, plain passes 7 and with the harness 9. It costs about 16 times the calls, and it lost one task that plain passed (t03). Repeat runs gave the same counts." |
| 2:10 | **Arena** (`arena.html`): a judge picks a challenge and tries to break plain Gemma | Operator starts it; Speaker narrates. Only a scored challenge where plain failed adds to the counter; free play says UNVERIFIED. |
| 2:40 | **Skill Doctor** (`doctor.html`), only if time allows: paste a skill, show the lint score | "Paste any skill and get a free risk estimate, no model call." |
| 2:50 | Close | "It is open source, the failure dataset is public, anyone can submit a failure with the issue form, and every claim here is one you can check." |

Read the numbers only from the real score page. If a MOCK banner is on screen, stop and fix it before presenting.
Say the cost out loud: about 16 times the calls. Say what we lost: t03. Judges trust a team that names its own limits.

## If the API fails

- X-ray, Fail Museum, Score page and the proof report need no API: they run from recordings and say REPLAY.
- Arena: the page shows the model error. Switch to the local-model fallback if one is set up (`ARENA_PROVIDER=local`, see `docs/ARENA_OPERATOR.md`), or demo the X-ray replay and say so: "The API is not responding right now, so this is a recording of an earlier run." Judges respect honesty more than silence.
- Live mode: click **Use recorded demo**.
- Rehearsal without internet: run the demo inputs once with `--cache`, then use `--replay` (0 API calls).

## If the Wi-Fi fails

Pages need no internet. Use the phone hotspot for the live API, or the recordings.

## Backup video

Record a 2-minute screen capture of the whole flow on Saturday (X-ray replay, score page, arena challenge, report download) and keep it on the laptop and on a phone. Shot list: Fail Museum failure, X-ray repair, Download report, Score page, Arena join and result.

## Checklist

- [ ] No MOCK banner on any page used.
- [ ] Recorded demo loads offline.
- [ ] Arena: `ARENA_MODE`, provider and the free-tier rate checked; one practice attempt run (`docs/ARENA_OPERATOR.md`).
- [ ] Phone hotspot ready, laptops charged.
- [ ] Dry run twice with a timer on Saturday.
