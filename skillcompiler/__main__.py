"""Command line: python -m skillcompiler compile|run SKILL.md ..."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import cache, providers
from .plan_io import load_plan, save_plan
from .runner import run_skill
from .splitter import compile_skill


def _add_cache_flags(p: argparse.ArgumentParser) -> None:
    p.add_argument("--cache", action="store_true",
                   help=f"cache model responses in {cache.DEFAULT_DIR}/ and reuse them")
    p.add_argument("--replay", action="store_true",
                   help="use only cached responses; never call the API (error on a miss)")
    p.add_argument("--cache-dir", default=cache.DEFAULT_DIR, help="cache folder")


def _add_provider_flags(p: argparse.ArgumentParser) -> None:
    p.add_argument("--provider", choices=providers.PROVIDERS, default=providers.GEMINI,
                   help="model provider (default gemini)")
    p.add_argument("--base-url", help="server URL for openai-compatible, "
                   "e.g. http://localhost:11434/v1 (Ollama); pair with --model")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="skillcompiler",
                                     description="Run long agent skills reliably on small models.")
    sub = parser.add_subparsers(dest="command", required=True)

    comp = sub.add_parser("compile", help="split a SKILL.md into a plan.json")
    comp.add_argument("skill", help="path to SKILL.md")
    comp.add_argument("-o", "--output", help="write the plan here (default: print)")
    comp.add_argument("--model", help="model name (default: GEMMA_MODEL from .env)")
    _add_cache_flags(comp)
    _add_provider_flags(comp)

    run = sub.add_parser("run", help="run a skill on an input and write a trace.json")
    run.add_argument("skill", help="path to SKILL.md")
    src = run.add_mutually_exclusive_group(required=True)
    src.add_argument("--input-file", help="file holding the user input")
    src.add_argument("--input", help="the user input as text")
    run.add_argument("--plan", help="use this saved plan (.json/.yaml) instead of splitting")
    _add_cache_flags(run)
    _add_provider_flags(run)
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
    if args.output:
        save_plan(plan, args.output)
        print(f"wrote {args.output}", file=sys.stderr)
    else:
        print(json.dumps(plan, indent=2, ensure_ascii=False))
    for warning in plan.get("warnings", []):
        print(f"warning: {warning}", file=sys.stderr)
    print(f"{len(plan['steps'])} steps", file=sys.stderr)
    return 0


def _cmd_run(args: argparse.Namespace) -> int:
    skill_text = Path(args.skill).read_text(encoding="utf-8")
    user_input = (Path(args.input_file).read_text(encoding="utf-8")
                  if args.input_file else args.input)
    plan = load_plan(args.plan) if args.plan else None
    trace = run_skill(skill_text, user_input.strip(), args.model,
                      max_retries=args.max_retries, verify=False if args.no_verify else None, plan=plan)
    for step in trace["steps"]:
        print(f"step {step['step_id']} {step['status']:<8} "
              f"({len(step['attempts'])} attempt) {step['title']}", file=sys.stderr)
    totals = trace["totals"]
    print(f"{totals['llm_calls']} calls, {totals['latency_ms'] / 1000:.1f}s, "
          f"{totals['retries']} retries, {totals['cache_hits']} cache hits", file=sys.stderr)
    if args.trace:
        _write_json(trace, args.trace)
    print(trace["final_output"])
    return 0


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8", errors="replace")
    args = build_parser().parse_args(argv)
    cache.configure(enabled=args.cache, replay=args.replay, directory=args.cache_dir)
    try:
        providers.configure(args.provider, args.base_url)
        return _cmd_compile(args) if args.command == "compile" else _cmd_run(args)
    except FileNotFoundError as exc:
        print(f"error: file not found: {exc.filename}", file=sys.stderr)
    except (RuntimeError, ValueError, cache.CacheMiss) as exc:  # e.g. no model, bad plan, replay miss
        print(f"error: {exc}", file=sys.stderr)
    except KeyError as exc:
        print(f"error: missing setting {exc}; copy .env.example to .env and fill it in",
              file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
