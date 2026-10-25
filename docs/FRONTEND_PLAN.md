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
  (module scripts are blocked on `file://`); the single-file build is meant to fix that. **Not yet verified here**: check it before relying on it.
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

I started a one-page trace-viewer prototype outside the repo (Thought Line header, a Status Mark per step, a Call Chip per attempt, a Replay button,
real `trace.json` files as input, paper-and-ink styling). At the time of writing it is **being built and has not been checked in a browser**.
I will say here when it has, and I can put the source in a new folder of the repo (not in `web/`) for you to look at.
The three sample traces it uses are in `skillcompiler/examples/traces/`.

## 9. Decisions for you

1. Restyle the existing HTML only, or build the React version? My view: restyle first, React for the trace viewer only if the prototype looks good to you.
2. Who builds it? If you are short on time I can build the trace viewer in a separate folder and you decide whether to swap it in.
3. Is the Commons Clause acceptable to you for a public repo that is entered as open source? If not, use the layout and motion ideas but write our own small CSS.
