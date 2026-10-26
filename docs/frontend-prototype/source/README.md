# Prototype source

React + Vite source of `../trace-viewer-demo.html`. Not part of `web/`; nothing here is used by the real pages yet.
Context and the decisions that need an answer are in [`../../FRONTEND_PLAN.md`](../../FRONTEND_PLAN.md).

## Build it

```bash
cd docs/frontend-prototype/source
npm install          # about 2 minutes: the icon package is large
npm run build        # a few seconds; writes dist/index.html, one self-contained file
```

Open `dist/index.html` by double-click. The **Recorded trace** tab works with no server. It reads the sample traces from
`skillcompiler/examples/traces/`, and you can load any `trace.json` with the file picker.

## Live tab

The **Live run** tab runs a skill through the harness and shows each step as it finishes. It needs the small server in this folder:

```bash
python server.py     # from this folder; serves http://127.0.0.1:5001
```

- Use a Python that has the repo's dependencies (`pip install -r skillcompiler/requirements.txt flask`) and a `.env` with your Gemini key in the repo root.
  On Windows, plain `python` in PowerShell can be a Store stub without those packages; the page then shows every attempt as failed with "No module named 'google.genai'".
- A run takes 40 to 90 seconds and uses real API calls (about 2 per step plus one to split the skill).
- The server streams the harness's `on_event` events as newline-delimited JSON (`skillcompiler/stream.py`). **Stop** ends the run at the next step boundary.
- It shows the harness only, not the plain-model comparison.

## Files

| File | Role |
|---|---|
| `src/App.jsx` | The two tabs, the recorded-trace view and the Replay button |
| `src/Live.jsx` | The live view: reads the event stream into step rows |
| `src/StepList.jsx` | The step list both views share (Status Mark per step, Call Chip per attempt) |
| `src/rb/` | Three React Bits components, copied unchanged, with their licence in `LICENSE.md` |
| `server.py` | Streaming endpoint for the Live tab (`/run-stream`) and the example skills (`/presets`) |

## If a build seems stuck

A build normally takes under 15 seconds. If one runs for more than a minute, stop it with `taskkill /F /T /PID <pid>` (the `/T` kills the whole tree;
killing only the parent can leave a Node process spinning on the CPU). On 25 Oct one build did hang that way and it could not be reproduced on 26 Oct; see the plan, section 8.
