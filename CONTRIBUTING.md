# Contributing

Thanks for helping. The easiest way to contribute is to **submit a failure**: open
[a new "Submit a failure" issue](https://github.com/Yasaswini-ch/skill-compiler/issues/new?template=submit_failure.yml)
and paste a skill, an input, and what the model got wrong.

## Setup

```
pip install -r skillcompiler/requirements.txt flask
cp .env.example .env      # then set GEMINI_API_KEY and GEMMA_MODEL
```

Never commit `.env` or an API key.

## Add a task

Tasks live in `benchmark/tasks.json`. Each task has a sample skill in `skills/`, one short user input and 4 to 7 checks that a script can verify.

1. Write or pick a `skills/<name>/SKILL.md` (frontmatter with `name` and `description`, then numbered steps).
2. Add an object to `benchmark/tasks.json` in the shape described in `contract/` (`task_id`, `title`, `skill_file`, `input`, `difficulty_tags`, `checks`).
3. Give each check a `label` from the list below and verify by hand that it passes on a correct answer and fails on a wrong one. A wrong check creates a fake failure.
4. Run `python tools/lint_skill.py skills/<name>/SKILL.md` to see how risky the skill is for small models. It checks rules L01 to L09 and prints a 0 to 100 score (under 25 low, under 55 medium, otherwise high).

## Run the benchmark

```
python -m benchmark.run_compare --limit 3      # quick check
python -m benchmark.run_compare                # all tasks
```

It writes `results.json` and `failures.json`. Copy them into `web/data/`, then run `python tools/sync_web_data.py` and open `web/index.html`.
If the harness is not connected, the files are marked as mock and every page shows a red MOCK DATA banner.

## Run the tests

```
python -m pytest skillcompiler/tests tools/tests
```

## Propose a label

The fixed labels are: `skipped_step`, `wrong_format`, `lost_track`, `merged_steps`, `hallucinated_step`, `ignored_constraint`, `other`.
To propose a new one, open an issue with a definition and at least two real examples. Changing labels or the file formats in `contract/` needs agreement from the three maintainers.

## Rules

- Report only numbers you measured. Mark mock data as mock.
- Keep changes inside the folder you are changing, and keep commits small with clear messages.
- No external CDN links in `web/`: the pages must work offline.
