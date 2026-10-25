"""Skill linter: flags steps likely to trip a small model. Pure Python, no LLM.

Usage: python tools/lint_skill.py path/to/SKILL.md [--json]
"""
import argparse
import difflib
import json
import re
import sys

VAGUE = ["appropriate", "as needed", "properly", "suitable", "relevant", "if necessary", "etc"]
FORMAT_WORDS = ["json", "table", "list", "words", "sentences", "format"]
# Points added to the 0-100 score for each finding of that rule.
WEIGHTS = {"L01": 15, "L02": 8, "L03": 12, "L04": 15, "L05": 6, "L06": 8, "L07": 8, "L08": 15, "L09": 30}
LOW, MEDIUM = 25, 55

NUMBERED = re.compile(r"^\s*(\d+)[.)]\s+(.*\S)")
HEADING = re.compile(r"^\s*#{2,6}\s+(.*\S)")


def strip_frontmatter(text: str) -> str:
    """Remove a leading YAML frontmatter block.

    Only strips when the first line is exactly "---", up to the next line that is exactly "---".
    An unclosed block is left alone.
    """
    lines = text.splitlines(keepends=True)
    if not lines or lines[0].rstrip("\r\n") != "---":
        return text
    for i in range(1, len(lines)):
        if lines[i].rstrip("\r\n") == "---":
            return "".join(lines[i + 1:])
    return text


def parse_steps(text: str) -> tuple[list[str], bool]:
    """Return (steps, numbered). Tries numbered lines, then headings, then paragraphs."""
    body = strip_frontmatter(text)
    lines = body.splitlines()
    steps: list[str] = []
    for line in lines:
        m = NUMBERED.match(line)
        if m:
            steps.append(m.group(2).strip())
        elif steps and line.strip() and line.startswith((" ", "\t")):
            steps[-1] += " " + line.strip()  # wrapped continuation of a numbered step
    if steps:
        return steps, True
    headings = [m.group(1).strip() for m in map(HEADING.match, lines) if m]
    if headings:
        return headings, False
    paras = [p.strip() for p in re.split(r"\n\s*\n", body) if p.strip() and not p.strip().startswith("#")]
    return paras, False


def _find(rule: str, step: int | None, message: str) -> dict:
    return {"rule": rule, "step": step, "message": message}


def lint(text: str) -> dict:
    """Return {"score", "level", "findings"} for a SKILL.md text."""
    steps, numbered = parse_steps(text)
    findings: list[dict] = []
    n = len(steps)
    if n == 0:
        findings.append(_find("L09", None, "No steps found. Write the skill as numbered steps (1., 2., 3.), one action each."))
    if n > 12:
        findings.append(_find("L01", None, f"{n} steps is a lot (high risk above 12): small models lose track. Split the skill."))
    elif n > 8:
        findings.append(_find("L01", None, f"{n} steps (warning above 8): consider splitting the skill."))
    for i, s in enumerate(steps, 1):
        words = len(s.split())
        low = s.lower()
        if words > 60:
            findings.append(_find("L02", i, f"Step is {words} words long (over 60). Shorten it to one action."))
        for v in VAGUE:
            if re.search(r"\b" + re.escape(v) + r"\b", low):
                findings.append(_find("L05", i, f'Vague wording "{v}": say exactly what to do.'))
        if "and then" in low or "after that" in low:
            findings.append(_find("L06", i, 'Two actions in one step ("and then" / "after that"). Make them separate steps.'))
        ifs = len(re.findall(r"\bif\b", low))
        if ifs > 1 or re.search(r"\bunless\b", low):
            findings.append(_find("L07", i, "Nested or tricky condition (several \"if\" or an \"unless\"). Spell out each case."))
    for i in range(n):
        for j in range(i + 1, n):
            ratio = difflib.SequenceMatcher(None, steps[i].lower(), steps[j].lower()).ratio()
            if ratio >= 0.6:
                findings.append(_find("L03", j + 1, f"Step {j + 1} is {ratio:.0%} similar to step {i + 1}: a model may merge or skip one."))
    if not any(w in text.lower() for w in FORMAT_WORDS):
        findings.append(_find("L04", None, "No output format is stated (json, table, list, word limit...). Say what the final output looks like."))
    if n and not numbered:
        findings.append(_find("L08", None, "Steps are not numbered. Number them 1., 2., 3. so each is one clear action."))
    score = min(100, sum(WEIGHTS[f["rule"]] for f in findings))
    level = "low" if score < LOW else "medium" if score < MEDIUM else "high"
    return {"score": score, "level": level, "steps": n, "findings": findings}


def format_text(report: dict) -> str:
    out = [f'Risk for small models: {report["level"].upper()} (score {report["score"]}/100, {report["steps"]} steps)']
    for f in report["findings"]:
        where = f'step {f["step"]}' if f["step"] else "skill"
        out.append(f'  {f["rule"]} [{where}] {f["message"]}')
    if not report["findings"]:
        out.append("  No findings.")
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("skill_file")
    ap.add_argument("--json", action="store_true", help="print the report as JSON")
    args = ap.parse_args(argv)
    with open(args.skill_file, encoding="utf-8") as fh:
        report = lint(fh.read())
    print(json.dumps(report, indent=2) if args.json else format_text(report))
    return 0


if __name__ == "__main__":
    sys.exit(main())
