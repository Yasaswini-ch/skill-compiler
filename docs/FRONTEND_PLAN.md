# Frontend plan: a stronger web UI with React Bits

For Likhitha (owner of `web/`). From Yasaswini, 25 Oct 2026. This is a proposal and a research result, not a change: nothing in `web/` was edited.

## 1. Why change anything

The pages work, the MOCK banners are right, and the wording is honest. The look is the weak part. It reads like a generic dashboard template:
dark rounded cards, pastel pills, a blue-purple accent, red and green bars, and one card style for everything. Judges see many of these.
The Fail Museum page is called a museum but looks like a SaaS dashboard, and the score page's red-vs-green bars say little.

## 2. Rules the new UI must keep (from your own design rules)

- No CDN and no internet needed at the venue. Everything is bundled.
- Opens from a folder or from `python web/server.py`.
- Same data files: `results.json`, `failures.json`, `trace.json`, `lint` JSON. The harness and the benchmark do not change.
- A red MOCK banner whenever `mock` or `harness_is_mock` is true. Final screenshots only from real data.
- Readable on a projector: big type, high contrast, nothing animated behind data.

## 3. Design direction: an incident archive

One idea for all pages, so it does not look like a template:

- Paper and ink: off-white page (dark variant for dark mode), ink text, thin rules instead of boxed cards. Square corners.
- Serif for headings (Georgia, no download), monospace for outputs and numbers.
- Colour only where it means something: green for pass, amber for repaired, red for fail. Failure labels get plain text, not six pastel colours.
- Every result shows where it came from: model, date, thinking setting, verifier on or off.
- Motion only for the thing being explained (a step running, a retry), never as background.

## 4. Components to use (React Bits, https://reactbits.dev)

React Bits has 217 free animated React components. About ten suit us. Descriptions below are the site's; I checked the three marked
(verified) by downloading their source, and I have not watched the others in motion, so preview each before committing to it.

| Page | Component | Use |
|---|---|---|
| Trace viewer, live | **Thought Line** (verified) | Run header with a live clock that folds into one line when done: "Ran 6 steps in 40 s" |
| Trace viewer, live | **Status Mark** (verified) | One glyph per step: idle ring, progress arc, then a check or a cross |
| Trace viewer, live | **Call Chip** (verified) | One chip per model call or attempt with a timer; ends green, or shakes red on a failed attempt |
| Trace viewer | Stepper, Animated List | Optional: step navigation |
| Score page | Count Up | The headline numbers |
| Score page | Split Flap Text | A departure-board "x of y" for plain vs harness |
| Score page | Fade Content | Reveal sections on scroll, subtly |
| Fail Museum | Flip Card | Front: what went wrong. Back: the model's output |
| Fail Museum | Folder | Each failure as a case file |
| Fail Museum | Tear Ticket, Scroll Stack, Spotlight Card | Optional exhibit styling |
| Landing header only | Faulty Terminal, CRT Warp or Dot Grid | One restrained background, with a still fallback |

Skip: the gradient and aurora backgrounds (Aurora, Gradient Waves, Grainient, Liquid Ether) because they are the common "AI template" look;
the cursor effects; the image galleries (Dome, Masonry, Circular, Chroma Grid, which needs photos) because we show text;
Fluid Glass (3D WebGL headline decoration).

## 5. Licence: read before copying code

React Bits uses **MIT + Commons Clause**. We may use components inside our app or website. We may not sell, sublicense or redistribute the
components themselves, alone or bundled. Our repo is public and MIT, so:

- put copied components in one folder (for example `web/app/src/reactbits/`) with React Bits' `LICENSE.md` next to them and keep each file's header;
- do not relicense them as ours; say in the README which files are third-party;
- keep the number small (about ten), since "open-source" is a judging track and Commons Clause is not an OSI open-source licence.

## 6. How it would be built

- Vite + React. Each component is plain source copied in. Download from the registry, for example
  `https://reactbits.dev/r/CallChip-JS-CSS.json` (works; the files are inside the JSON), or `npx shadcn@latest add @react-bits/CallChip-JS-CSS`.
  The three verified components need two npm packages: `motion` and `@hugeicons/react` with `@hugeicons/core-free-icons`.
- Build to **one self-contained HTML file** with `vite-plugin-singlefile`. A normal Vite build does not open from a folder in Chrome
  (module scripts are blocked on `file://`); the single-file build fixes that. **Verified on 25 Oct**: the prototype's built file (330 KB, script and
  styles inlined) loaded straight from disk in headless Chrome on Windows with no server, and React rendered it fully. Not tested in other browsers.
- Load JSON by file picker or bundled sample, as the viewer already does, so it works without a server. Same file shapes as `contract/`.
- Keep the current pages until the new ones are checked on real data. Swap per page, not all at once.

## 7. Suggested order and time

1. Trace viewer (Thought Line, Status Mark, Call Chip, a Replay button): about 3 hours. This is the best fit and a good test of the whole idea.
2. Live page: same pieces, once the harness can report each step as it finishes. I can add that (an `on_event` callback in `run_skill`, about 1 to 2 hours on my side).
3. Score page: about 2 hours.
4. Fail Museum: about 3 hours.
5. README screenshots from real data after Sriya's numbers exist.

Features freeze on Friday night. If the trace viewer is not clearly better by Wednesday, stop and keep the current pages with the restyle in section 3 only (CSS changes, no React).
The restyle alone is a smaller job and fixes most of what looks off.

## 8. Prototype status

I built a one-page trace-viewer prototype outside the repo and checked it in a browser on 25 Oct. It has a Thought Line header, a Status Mark per step,
a Call Chip per attempt, a **Replay** button, a file picker for any `trace.json`, and paper-and-ink styling (light and dark). It uses the three real traces in
`skillcompiler/examples/traces/`, including the `gemma3:4b` run with pass, repaired and fail steps.

What was checked: it renders from the built single file with no console errors; Replay plays the run back (a failed attempt gets a red chip and its checker note,
then the retry turns green) and the header settles on the real recorded time ("Ran 6 steps in 39.4s"), not the sped-up replay time; step states and counts match the trace.
Setup took 2 minutes for npm (the icon package is large) and the build takes a few seconds. The page is 330 KB.

Things the prototype taught us:
- **Call Chip only styles a failure when it moves from running to failed.** A chip mounted already failed looks unstyled, so the prototype mounts every chip as running and
  settles it a moment later. A failed attempt shows a "retry" arrow icon by design, including the last attempt of a step that finally failed.
- **Show real latency yourself.** The chip's own timer shows replay time, so the prototype turns it off and writes the recorded latency into the label.
- The trace viewer must accept a trace with no `totals.cache_hits` (older traces).
- Not yet done: the score page, the museum, keyboard and reduced-motion checks.

**Try it:** open `docs/frontend-prototype/trace-viewer-demo.html` (double-click; one file, works offline). See that folder's README.

**Live view, status on 25 Oct:** the harness side is done and tested. `run_skill(..., on_event=callback)` now reports `run_start`, `plan`, `step_start`, `attempt_start`,
`attempt_end`, `step_end` and `run_end` as a run progresses, and `skillcompiler/stream.py` turns that into newline-delimited JSON for a web route
(three lines in Flask; the docstring has the example), including a cancel when the browser disconnects. 111 tests pass.
The page that uses it (a Live tab with steps appearing as they finish, a Stop button, and a download of the trace) is written, but **its build hung twice**
in the transform step with a Node process spinning on the CPU, so it has not been run and is not in the repo. The cause is not known yet (my code or the build tool).
Until it is found, do not build it on your machine; I will say here when it is resolved.

I have not added the prototype source to the repo, because it includes React Bits files and the licence question in section 5 is yours to decide,
and because of the build problem above.

## 9. Decisions for you

1. Restyle the existing HTML only, or build the React version? My view: restyle first, React for the trace viewer only if the prototype looks good to you.
2. Who builds it? If you are short on time I can build the trace viewer in a separate folder and you decide whether to swap it in.
3. Is the Commons Clause acceptable to you for a public repo that is entered as open source? If not, use the layout and motion ideas but write our own small CSS.
