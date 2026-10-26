# Trace viewer prototype (try it)

`trace-viewer-demo.html` is one self-contained page. **Double-click it to open it**: no install, no server, no internet.

What it is: a possible new look for the trace viewer, built with React and three React Bits components
(Thought Line, Status Mark, Call Chip). It is a prototype for discussion, not part of `web/`.
The plan and the reasons are in [`../FRONTEND_PLAN.md`](../FRONTEND_PLAN.md).

## Try this

1. Pick a sample from the dropdown: a `gemma3:4b` run with pass, repaired and failed steps; a `gemma-4-26b` run with one repair; a 12-step run with no retries.
2. Press **Replay (sped up)**. Each attempt runs, a failed one turns red with the checker's note, and the retry turns green.
   The header clock settles on the real recorded time, not the sped-up replay time.
3. Press **Open a trace.json** and load any real trace (`python -m skillcompiler run ... --trace trace.json`).
4. Look at it in light and dark mode (it follows the system setting).

## What was checked (25 Oct 2026)

- Loaded straight from disk in headless Chrome on Windows with no server: the page renders fully (title, 6 steps, 12 attempt chips, no console errors).
- Rendered in the browser pane from a local server, with no console errors; Replay and the sample switch work.
- Not checked: other browsers, keyboard use, reduced motion, small phone screens.

## Live tab (needs a server)

The second tab, **Live run**, runs a skill through the harness and shows each step as it finishes, with a Stop button and a download of the trace.
In the double-click demo it will say it cannot reach the server; to use it, start `python server.py` from [`source/`](source/README.md).
Checked on 26 Oct with a real run of `ticket-triage`: the plan appeared, steps filled in one by one, and it ended with "Ran 6 steps in 38.8s",
6 of 6 passed first try, 13 model calls, and the trace downloadable. Also checked: with no working model, every attempt shows as failed with its error and the page does not crash.
Source and build steps: [`source/`](source/README.md).

## Third-party code

The page and the source in `source/` include code from **React Bits** (https://reactbits.dev), licensed MIT + Commons Clause. The licence text is in
[`REACT-BITS-LICENSE.md`](REACT-BITS-LICENSE.md). The Commons Clause forbids selling or redistributing those components on their own or in a bundle;
using them inside an application is allowed. Whether that is acceptable for this repository is an open question in `FRONTEND_PLAN.md`, section 5.
