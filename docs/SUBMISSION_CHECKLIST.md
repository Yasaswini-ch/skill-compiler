# Submission checklist (from the event page)

Submit by **3:45 PM**, not 4:14. All three check the confirmation.

- [ ] **Title:** Skill Compiler + Gemma Fail Museum
- [ ] **Description** (what it is, who it helps, how it uses Gemma 4 and open source):
  > An open-source harness that makes small open models like Gemma 4 follow long agent skills reliably, by splitting a skill into steps, checking every output and retrying with feedback. It comes with a public benchmark and a labelled dataset of how plain Gemma fails, a skill linter, and web pages to explore it. It helps anyone writing agent skills for small open models. Gemma 4 (via the Gemini API) does the splitting, running and verifying. Results: [PLAIN x/y] vs [HARNESS x/y] on [N] tasks.
- [ ] **Demo link or video:** [LINK]
- [ ] **Repo link** (public, license visible): https://github.com/Yasaswini-ch/skill-compiler. Check in a private window.
- [ ] **Screenshots** (real data, no MOCK banner): score page, Fail Museum, trace viewer with a retry, live mode.
- [ ] **Tools used:** Gemma 4 via the Gemini API, Python, Flask, pytest, plain HTML/CSS/JS.
- [ ] **Prize tracks:** Best Open-Source AI Project, Best Use of Gemma 4.

## Before submitting

- [ ] `v1.0` tag pushed after the 3:00 PM freeze.
- [ ] README quickstart tested by someone else on a clean clone.
- [ ] Dataset link opens and the dataset card has real numbers.
- [ ] No placeholder in square brackets is left in README, write-up or description.
- [ ] Every number matches `web/data/results.json`.
