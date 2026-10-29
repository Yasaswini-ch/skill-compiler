# Skill Compiler Chrome extension

Right-click selected text, pick a skill, and watch the harness run it step by step. Each step shows passed, repaired (first try rejected, with the checker's reason) or failed.

**No API key is in the extension.** The extension sends the selected text and the skill only to `http://127.0.0.1:5000`, the Skill Compiler server on your own computer. That server calls the model with the key in its `.env`. Nothing is saved.

## Load it (Chrome or another Chromium browser)

1. Start the server from the repo root: `python web/server.py` (it needs `.env` with `GEMINI_API_KEY` and `GEMMA_MODEL`, as in the main README).
2. Open `chrome://extensions` and switch on **Developer mode** (top right).
3. Click **Load unpacked** and choose this `extension/` folder.
4. Select some text on any page, right-click, and choose **Run a skill on this selection**.
5. A small window opens. Read the first-run notice and click **OK, I understand** (shown once).
6. Pick a skill, click **Run**.

If the server is off the panel says so and tells you the command to start it.

## What it can do

- Skills are the `.md` files in `skills/` (listed in `skills/index.json`): `email-to-action-items` and `rubric-checker`. To add one, drop a `SKILL.md`-style file in `skills/` and add a line to `index.json`. A skill may have at most 6 steps and 6000 characters.
- The selection may be at most 1500 characters (longer text is cut, and the panel says so).
- **Download events** saves the run as NDJSON. Open `http://127.0.0.1:5000/xray.html`, choose "Or load a file", and pick it to see the run in the full X-ray view.
- One run at a time. A second run while one is going gets "Another run is using the model right now."
- Runs use adaptive mode and stop after 240 s. Set `EXTENSION_MODE` (`full`, `adaptive`, `auto`) and `EXTENSION_TIMEOUT` (seconds) in the server's environment to change that. On the free API tier a run can take a few minutes.

## Permissions

`contextMenus` (the right-click item), `activeTab`, `storage` (remembers the selection for the panel and that you read the notice), and host access to `http://127.0.0.1:5000/*` only. The test `extension/tests/panel-core.test.js` fails if this list grows or if an API key appears in these files.

## Files

| File | Purpose |
|---|---|
| `manifest.json` | Manifest V3 |
| `background.js` | right-click item, opens the panel |
| `panel.html`, `panel.css`, `panel.js` | the panel |
| `panel-core.js` | logic without the page (tested with Node: `node --test extension/tests/panel-core.test.js`) |
| `skills/` | the bundled skills |
| `../web/extension.py` | the server route `/extension/run` (tests: `tools/tests/test_extension.py`) |

## Checked

Loaded unpacked in Chrome on 29 Oct 2026 and run on the real API with both bundled skills (all steps passed, about 100 to 120 s each on the free tier). The downloaded events load in the X-ray logic. The long-selection case was also run (the input was cut to about 1500 characters) and you confirmed the server-off message works.
