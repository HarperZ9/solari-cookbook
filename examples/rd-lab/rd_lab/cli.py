import argparse
import json
from pathlib import Path
import sys

from .engine import run_mission
from .run_room import render_report
from .validation import ValidationError, load_mission


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    if args.command == "run":
        return _run(args.mission, args.out, args.inspect_symbol)
    parser.print_help()
    return 2


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m rd_lab")
    subparsers = parser.add_subparsers(dest="command")
    run_parser = subparsers.add_parser("run", help="run a local trusted mission")
    run_parser.add_argument("mission", help="path to mission JSON")
    run_parser.add_argument("--out", required=True, help="output directory")
    run_parser.add_argument("--inspect-symbol", help="optional source lookup using installed Index")
    return parser


def _run(mission_path: str, out_path: str, inspect_symbol: str | None = None) -> int:
    try:
        inspection = _inspect(mission_path, inspect_symbol) if inspect_symbol else None
        report = run_mission(mission_path, out_path)
        if inspection is not None:
            report["source_inspection"] = inspection
            (Path(out_path) / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
        with (Path(out_path) / "index.html").open("x", encoding="utf-8") as view:
            view.write(render_report(report))
    except (ValidationError, ValueError, RuntimeError, OSError) as exc:
        print(f"run error: {exc}", file=sys.stderr)
        return 2
    print(Path(out_path) / "index.html")
    return 0


def _inspect(mission_path: str, query: str) -> dict:
    from .source_inspection import inspect_sources
    mission = load_mission(mission_path)
    programs = [mission.baseline, *(candidate.program for candidate in mission.candidates)]
    files = list(dict.fromkeys(program.rel_path for program in programs))
    return inspect_sources(mission.root, files, query)
