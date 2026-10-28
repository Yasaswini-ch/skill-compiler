"""Ask Gemma for harder variants of the hand-written tasks. Writes benchmark/tasks_generated.json.

    python -m benchmark.gen_variants [--only t01,t02] [--limit N] [--out FILE] [--variants 3]
    python -m benchmark.gen_variants --review 10 [--seed 1]     # print random generated tasks for hand-checking

For each task in tasks.json, Gemma gets the skill and the task and writes 3 harder variants (same skill, new
input, new checks). Every returned task is validated against the tasks.json schema; invalid ones are dropped and
counted. tasks.json is only read, never written.

What this script sets itself (and does not trust the model with): task_id (<source id>-v1..v3), skill_file (the
source task's), source_task_id and generated: true. A generated check can still be WRONG even if it is valid:
a person must hand-check a sample (--review) before the generated results are used. Generated tasks live in their
own file and are never added to the official results.
"""
from __future__ import annotations

import argparse
import json
import random
import re
import sys
import time
from datetime import datetime
from pathlib import Path

from benchmark import client
from benchmark.run_plain import load_tasks, read_skill
from benchmark.scorer import CHECKS

BENCH = Path(__file__).resolve().parent
TASKS_FILE = BENCH / "tasks.json"
DEFAULT_OUT = BENCH / "tasks_generated.json"
DROPPED_LOG = BENCH / "output" / "generated" / "dropped_variants.json"
LABELS = {"skipped_step", "wrong_format", "lost_track", "merged_steps", "hallucinated_step",
          "ignored_constraint", "other"}
TAGS = {"similar_steps", "strict_format", "step_order", "hard_limits", "arithmetic", "long_instructions"}
CHECK_KEYS = {"id", "type", "label", "value", "path", "case_sensitive", "whole_word"}
MIN_CHECKS, MAX_CHECKS, MAX_INPUT_CHARS = 4, 7, 2000

PROMPT = """Here is an agent skill and one task that tests it.

SKILL:
{skill_text}

TASK:
{task_json}

Write {n} harder variants of this task. Keep the same skill, but change the input so a small model is more likely to fail: add a distracting detail, make two steps sound similar, add a strict length limit, require a specific output format, or make step order matter. Every variant needs 4 to 7 checks that a script can verify, adjusted to the new input.

Return ONLY a JSON array of {n} task objects, no other text. Each object has exactly these keys: "title", "input", "difficulty_tags", "checks".
- difficulty_tags: a non-empty list from {tags}.
- checks: a list of objects with "id" ("c1", "c2", ...), "type", "label" and the fields the type needs.
- label: one of {labels}.
- check types and their fields:
  json_valid (no value); json_keys (value: list of the exact keys); one_of (value: list of allowed strings; optional path);
  max_words and min_words (value: integer; optional path); starts_with, contains, not_contains (value: string; optional path);
  regex (value: a Python regular expression; optional path); order (value: list of at least 2 strings that must appear in that order; optional path).
- "path" is a dot path into the parsed JSON output, for example "reply" or "items.0.name". Without a path the check applies to the whole output.
- Work out the correct answer for your new input yourself, and make sure the checks accept it. Do not write checks that no correct answer could pass.
"""


# --- validation ---------------------------------------------------------------------------------

def _is_int(v) -> bool:
    return isinstance(v, int) and not isinstance(v, bool)


def _nonempty_str(v) -> bool:
    return isinstance(v, str) and v.strip() != ""


def validate_check(c) -> list[str]:
    """Problems with one check (empty list = valid)."""
    if not isinstance(c, dict):
        return ["check is not an object"]
    p = []
    extra = set(c) - CHECK_KEYS
    if extra:
        p.append(f"unknown check keys {sorted(extra)}")
    if not _nonempty_str(c.get("id")):
        p.append("check without an id")
    typ = c.get("type")
    if typ not in CHECKS:
        return p + [f"unknown check type {typ!r}"]
    if c.get("label") not in LABELS:
        p.append(f"{c.get('id')}: label {c.get('label')!r} is not one of the 7 labels")
    if "path" in c and not _nonempty_str(c["path"]):
        p.append(f"{c.get('id')}: empty path")
    for flag in ("case_sensitive", "whole_word"):
        if flag in c and not isinstance(c[flag], bool):
            p.append(f"{c.get('id')}: {flag} must be true or false")
    v = c.get("value")
    if typ == "json_valid":
        if "value" in c:
            p.append(f"{c.get('id')}: json_valid takes no value")
    elif typ in ("json_keys", "one_of", "order"):
        need = 2 if typ == "order" else 1
        if not (isinstance(v, list) and len(v) >= need and all(_nonempty_str(x) for x in v)):
            p.append(f"{c.get('id')}: {typ} needs a list of at least {need} non-empty strings")
    elif typ in ("max_words", "min_words"):
        if not (_is_int(v) and v >= 1):
            p.append(f"{c.get('id')}: {typ} needs an integer of at least 1")
    elif typ == "regex":
        if not _nonempty_str(v):
            p.append(f"{c.get('id')}: regex needs a pattern")
        else:
            try:
                re.compile(v)
            except re.error as exc:
                p.append(f"{c.get('id')}: bad regex ({exc})")
    elif not _nonempty_str(v):  # starts_with, contains, not_contains
        p.append(f"{c.get('id')}: {typ} needs a non-empty string value")
    return p


def validate_task(t, source: dict | None = None, seen_inputs: set[str] | None = None) -> list[str]:
    """Problems with a generated task body (title, input, difficulty_tags, checks). Empty list = valid."""
    if not isinstance(t, dict):
        return ["task is not an object"]
    p = []
    extra = set(t) - {"title", "input", "difficulty_tags", "checks", "task_id", "skill_file"}
    if extra:
        p.append(f"unknown task keys {sorted(extra)}")
    if not _nonempty_str(t.get("title")):
        p.append("missing title")
    inp = t.get("input")
    if not _nonempty_str(inp):
        p.append("missing input")
    else:
        if len(inp) > MAX_INPUT_CHARS:
            p.append(f"input is longer than {MAX_INPUT_CHARS} characters")
        if source and inp.strip() == source["input"].strip():
            p.append("input is identical to the source task's input")
        if seen_inputs is not None and inp.strip() in seen_inputs:
            p.append("input duplicates another variant")
    tags = t.get("difficulty_tags")
    if not (isinstance(tags, list) and tags and all(x in TAGS for x in tags)):
        p.append(f"difficulty_tags must be a non-empty list from {sorted(TAGS)}")
    if source and t.get("skill_file") not in (None, source["skill_file"]):
        p.append("skill_file differs from the source task's skill")
    checks = t.get("checks")
    if not (isinstance(checks, list) and MIN_CHECKS <= len(checks) <= MAX_CHECKS):
        p.append(f"checks must be a list of {MIN_CHECKS} to {MAX_CHECKS}")
    else:
        for c in checks:
            p += validate_check(c)
        ids = [c.get("id") for c in checks if isinstance(c, dict)]
        if len(set(ids)) != len(ids):
            p.append("duplicate check ids")
    return p


# --- generation ---------------------------------------------------------------------------------

def extract_json_array(text: str):
    """Parse the model's reply as a JSON array (a code fence around it is allowed). None if it is not one."""
    s = (text or "").strip()
    fence = re.match(r"\A```[A-Za-z0-9_-]*[ \t]*\r?\n(.*?)\r?\n?```\Z", s, re.DOTALL)
    s = fence.group(1).strip() if fence else s
    try:
        data = json.loads(s)
    except ValueError:
        start, end = s.find("["), s.rfind("]")
        if start < 0 or end <= start:
            return None
        try:
            data = json.loads(s[start:end + 1])
        except ValueError:
            return None
    return data if isinstance(data, list) else None


def build_prompt(skill_text: str, task: dict, n: int) -> str:
    shown = {k: task[k] for k in ("title", "input", "difficulty_tags", "checks")}
    return PROMPT.format(skill_text=skill_text.strip(), task_json=json.dumps(shown, indent=2, ensure_ascii=False),
                         n=n, tags=sorted(TAGS), labels=sorted(LABELS))


def generate_for_task(task: dict, skill_text: str, n: int = 3, call=None, model: str | None = None):
    """Returns (valid tasks, dropped). `dropped` is a list of {"source_task_id", "reason", "raw"}.

    One retry if the reply is not a JSON array. If it still is not, all n variants count as dropped.
    """
    call = call or client.call_llm
    data = None
    for _ in range(2):
        data = extract_json_array(call(build_prompt(skill_text, task, n), model))
        if data is not None:
            break
    if data is None:
        return [], [{"source_task_id": task["task_id"], "reason": "reply was not a JSON array", "raw": None}] * n
    valid, dropped, seen = [], [], set()
    for pos, raw in enumerate(data[:n], 1):
        problems = validate_task(raw, task, seen)
        if problems:
            dropped.append({"source_task_id": task["task_id"], "reason": "; ".join(problems), "raw": raw})
            continue
        seen.add(raw["input"].strip())
        valid.append({
            "task_id": f"{task['task_id']}-v{pos}",
            "title": raw["title"].strip(), "skill_file": task["skill_file"], "input": raw["input"].strip(),
            "difficulty_tags": raw["difficulty_tags"], "checks": raw["checks"],
            "source_task_id": task["task_id"], "generated": True,
        })
    for _ in range(n - len(data[:n])):  # the model returned fewer than asked for
        dropped.append({"source_task_id": task["task_id"], "reason": "model returned fewer variants than requested", "raw": None})
    return valid, dropped


def review_sample(tasks: list[dict], n: int, seed: int) -> str:
    """Readable text for hand-checking n random generated tasks."""
    pick = random.Random(seed).sample(tasks, min(n, len(tasks)))
    lines = []
    for t in sorted(pick, key=lambda x: x["task_id"]):
        lines += [f"=== {t['task_id']} (from {t['source_task_id']}) {t['title']}", f"tags: {t['difficulty_tags']}",
                  f"input: {t['input']}", "checks:"]
        for c in t["checks"]:
            extras = {k: v for k, v in c.items() if k not in ("id", "type", "label")}
            lines.append(f"  {c['id']} [{c['label']}] {c['type']} {json.dumps(extras, ensure_ascii=False)}")
        lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Generate harder task variants with Gemma.")
    ap.add_argument("--only", help="comma-separated source task ids")
    ap.add_argument("--limit", type=int, help="only the first N tasks")
    ap.add_argument("--variants", type=int, default=3, help="variants per task (default 3)")
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--sleep", type=float, default=2.0, help="seconds between calls (default 2)")
    ap.add_argument("--review", type=int, metavar="N", help="print N random tasks from --out for hand-checking and exit")
    ap.add_argument("--seed", type=int, default=1, help="seed for --review (default 1)")
    args = ap.parse_args(argv)
    if args.out.resolve() == TASKS_FILE.resolve():
        print("error: --out must not be tasks.json (the frozen tasks)", file=sys.stderr)
        return 1
    if args.review:
        print(review_sample(json.loads(args.out.read_text(encoding="utf-8")), args.review, args.seed))
        return 0
    tasks = load_tasks(TASKS_FILE)
    if args.only:
        tasks = [t for t in tasks if t["task_id"] in set(args.only.split(","))]
    tasks = tasks[: args.limit] if args.limit else tasks
    generated, dropped = [], []
    for task in tasks:
        print(f"{task['task_id']} ...", flush=True)
        ok, bad = generate_for_task(task, read_skill(task), args.variants)
        generated += ok
        dropped += bad
        print(f"  valid {len(ok)}, dropped {len(bad)}", flush=True)
        time.sleep(args.sleep)
    args.out.write_text(json.dumps(generated, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    DROPPED_LOG.parent.mkdir(parents=True, exist_ok=True)
    DROPPED_LOG.write_text(json.dumps(
        {"generated_at": datetime.now().astimezone().isoformat(timespec="seconds"), "model": client.current_model(),
         "dropped": dropped}, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    asked = len(tasks) * args.variants
    print(f"\nasked for {asked}, valid {len(generated)}, dropped {len(dropped)}  ->  {args.out}"
          f"\ndropped details: {DROPPED_LOG}\nNext: hand-check at least 10 random tasks (--review 10).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
