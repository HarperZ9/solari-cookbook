import json
import os
import subprocess
import sys
import textwrap
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2), encoding="utf-8")


def write_program(path, source):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(source).lstrip(), encoding="utf-8")


def run_lab(mission_path, out_path, timeout=10):
    env = {
        "PATH": os.environ.get("PATH", ""),
        "PYTHONPATH": str(ROOT),
        "PYTHONIOENCODING": "utf-8",
    }
    return subprocess.run(
        [sys.executable, "-m", "rd_lab", "run", str(mission_path), "--out", str(out_path)],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        timeout=timeout,
    )


def load_report(path):
    return json.loads((path / "report.json").read_text(encoding="utf-8"))


def simple_mission(root, *, cases=None, candidates=None, baseline_source=None):
    mission_root = root / "mission"
    mission_root.mkdir()
    write_program(
        mission_root / "baseline.py",
        baseline_source
        or """
        import json
        import sys
        payload = json.load(sys.stdin)
        print(json.dumps({"value": payload.get("value")}))
        """,
    )
    write_json(
        mission_root / "mission.json",
        {
            "schema": "rd-lab.mission/v1",
            "name": "simple",
            "baseline": "baseline.py",
            "candidates": candidates or [],
            "cases": cases
            if cases is not None
            else [{"id": "one", "input": {"value": 2}, "expected": {"value": 4}}],
            "timeout_seconds": 1,
        },
    )
    return mission_root


def wrong_output_mission(work):
    mission_root = work / "mission"
    mission_root.mkdir()
    write_program(mission_root / "baseline.py", "import json, sys\njson.load(sys.stdin)\nprint(json.dumps({'value': 'baseline'}))")
    write_program(mission_root / "wrong.py", "import json, sys\njson.load(sys.stdin)\nprint(json.dumps({'value': 'wrong'}))")
    write_json(
        mission_root / "mission.json",
        {
            "schema": "rd-lab.mission/v1",
            "name": "wrong-output",
            "baseline": "baseline.py",
            "candidates": [{"id": "wrong", "program": "wrong.py"}],
            "cases": [
                {
                    "id": "literal",
                    "input": {"value": "input-only"},
                    "expected": {"value": "expected"},
                }
            ],
            "timeout_seconds": 1,
        },
    )
    return mission_root


def visibility_mission(work):
    mission_root = work / "mission"
    mission_root.mkdir()
    write_program(mission_root / "baseline.py", "import json; print(json.dumps({}))")
    write_program(
        mission_root / "snoop.py",
        """
        import json, pathlib, sys
        payload = json.load(sys.stdin)
        marker = "-".join(["oracle", "secret"])
        leaked = marker in json.dumps(payload)
        for path in pathlib.Path(".").rglob("*"):
            if path.is_file():
                leaked = leaked or marker in path.read_text(encoding="utf-8", errors="ignore")
        print(json.dumps({"leaked": True, "marker": marker} if leaked else {"leaked": False}))
        """,
    )
    write_json(
        mission_root / "mission.json",
        {
            "schema": "rd-lab.mission/v1",
            "name": "input-visibility",
            "baseline": "baseline.py",
            "candidates": [{"id": "snoop", "program": "snoop.py"}],
            "cases": [
                {
                    "id": "secret",
                    "input": {"visible": "candidate-input"},
                    "expected": {"leaked": True, "marker": "oracle-secret"},
                }
            ],
            "timeout_seconds": 1,
        },
    )
    return mission_root
