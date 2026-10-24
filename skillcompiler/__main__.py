"""Command line: python -m skillcompiler compile|run SKILL.md ..."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .runner import run_skill
from .splitter import compile_skill


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="skillcompiler",
                                     description="Run long agent skills reliably on small models.")
    sub = parser.add_subparsers(dest="command", required=True)

    comp = sub.add_parser("compile", help="split a SKILL.md into a plan.json")
    comp.add_argument("skill", help="path to SKILL.md")
    comp.add_argument("-o", "--output", help="write the plan here (default: print)")
    comp.add_argument("--model", help="model name (default: GEMMA_MODEL from .env)")

    run = sub.add_parser("run", help="run a skill on an input and write a trace.json")
    run.add_argument("skill", help="path to SKILL.md")
    src = run.add_mutually_exclusive_group(required=True)
    src.add_argument("--input-file", help="file holding the user input")
    src.add_argument("--input", help="the user input as text")
    run.add_argument("--trace", help="write the trace here (default: not saved)")
    run.add_argument("--model", help="model name (default: GEMMA_MODEL from .env)")
    run.add_argument("--max-retries", type=int, default=2, help="retries per step (default 2)")
    run.add_argument("--no-verify", action="store_true",
                     help="format check only, skip the model verification call")
    return parser


def _write_json(data: dict, path: str | None) -> None:
    text = json.dumps(data, indent=2, ensure_ascii=False)
    if path:
        Path(path).write_text(text + "\n", encoding="utf-8")
        print(f"wrote {path}", file=sys.stderr)
    else:
        print(text)


def _cmd_compile(args: argparse.Namespace) -> int:
    skill_path = Path(args.skill)
    plan = compile_skill(skill_path.read_text(encoding="utf-8"), args.model,
                         source_file=skill_path.as_posix())
    _write_json(plan, args.output)
    print(f"{len(plan['steps'])} steps", file=sys.stderr)
    return 0


def _cmd_run(args: argparse.Namespace) -> int:
    skill_text = Path(args.skill).read_text(encoding="utf-8")
    user_input = (Path(args.input_file).read_text(encoding="utf-8")
                  if args.input_file else args.input)
    trace = run_skill(skill_text, user_input.strip(), args.model,
                      max_retries=args.max_retries, verify=not args.no_verify)
    for step in trace["steps"]:
        print(f"step {step['step_id']} {step['status']:<8} "
              f"({len(step['attempts'])} attempt) {step['title']}", file=sys.stderr)
    totals = trace["totals"]
    print(f"{totals['llm_calls']} calls, {totals['latency_ms'] / 1000:.1f}s, "
          f"{totals['retries']} retries", file=sys.stderr)
    if args.trace:
        _write_json(trace, args.trace)
    print(trace["final_output"])
    return 0


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8", errors="replace")
    args = build_parser().parse_args(argv)
    try:
        return _cmd_compile(args) if args.command == "compile" else _cmd_run(args)
    except FileNotFoundError as exc:
        print(f"error: file not found: {exc.filename}", file=sys.stderr)
    except RuntimeError as exc:  # e.g. no model configured
        print(f"error: {exc}", file=sys.stderr)
    except KeyError as exc:
        print(f"error: missing setting {exc}; copy .env.example to .env and fill it in",
              file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
