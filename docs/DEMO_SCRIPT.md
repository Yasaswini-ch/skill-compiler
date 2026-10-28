# Demo script (3 minutes)

Roles: **Speaker** talks. **Operator** (Yasaswini) runs live mode. **Number-answerer** (Sriya) takes questions about results and method.
Before going on: open `web/server.py` running, tabs ready for `museum.html`, `trace.html`, `index.html`, `live.html`. Real data in `web/data/`, no MOCK banner visible.

| Time | What happens | Say |
|---|---|---|
| 0:00 | Problem | "Small models skip steps when you give them a long list of instructions, and they do it silently." |
| 0:20 | **Fail Museum** (`museum.html`): open two real failures from plain Gemma | "Here plain Gemma added up an invoice wrongly: the subtotal and the tax did not match (task t04, failure f002). Here it got one row of a scaled recipe table wrong (task t08, failure f004). These are real outputs, labelled and in a public dataset." |
| 1:00 | **Trace viewer** (`trace.html`): a run with a retry | "The harness gives one step at a time. This step failed its format check, got the checker's note, tried again, and passed." |
| 1:40 | **Score page** (`index.html`) | "On 10 tasks, plain passes 7 and with the harness 9. It costs about 16 times the calls, and it lost one task that plain passed. Two repeat runs gave the same counts." |
| 2:10 | **Live mode** (`live.html`): a judge types a task, plain and harness run side by side | Operator runs it; Speaker narrates while it runs. |
| 2:50 | Close | "It is open source, the failure dataset is public, and anyone can submit a failure with the issue form." |

Read the numbers only from the real score page. If a MOCK banner is on screen, stop and fix it before presenting.

## If the API fails

Click **Use recorded demo** in live mode and say so: "The API is not responding right now, so this is a recording of an earlier run." Judges respect honesty more than silence.
For rehearsal without internet, run the demo inputs once with `--cache`, then use `--replay` (0 API calls).

## If the Wi-Fi fails

Pages need no internet. Use the phone hotspot for the live API, or the recorded demo.

## Checklist

- [ ] No MOCK banner on any page used.
- [ ] Recorded demo loads offline.
- [ ] Phone hotspot ready, laptops charged.
- [ ] Dry run twice with a timer on Saturday.
