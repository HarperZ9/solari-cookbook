import argparse
import sys

from .engine import run_mission
from .validation import ValidationError


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    if args.command == "run":
        return _run(args.mission, args.out)
    parser.print_help()
    return 2


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m rd_lab")
    subparsers = parser.add_subparsers(dest="command")
    run_parser = subparsers.add_parser("run", help="run a local trusted mission")
    run_parser.add_argument("mission", help="path to mission JSON")
    run_parser.add_argument("--out", required=True, help="output directory")
    return parser


def _run(mission_path: str, out_path: str) -> int:
    try:
        run_mission(mission_path, out_path)
    except ValidationError as exc:
        print(f"validation error: {exc}", file=sys.stderr)
        return 2
    return 0
