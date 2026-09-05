import json
import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .evaluation import evaluate_case, experiment_passed, sha256_file, unified_diff
from .execution import run_program
from .validation import Candidate, Mission, ProgramRef, ValidationError, load_mission


RUN_SCHEMA = "rd-lab.run/v1"
EXECUTION_MODE = "local_trusted_subprocess"
LIMITATIONS = [
    "Local subprocess execution is trusted-code-only and is not a security sandbox.",
    "Supplied repair candidates are fixture-defined; no autonomous discovery is claimed.",
    "No cloud execution, public upload, or model call is performed by this engine.",
]


def run_mission(mission_path: str | Path, out_path: str | Path) -> dict[str, Any]:
    mission = load_mission(mission_path)
    out_dir = _prepare_output_dir(out_path)
    started_at = _utc_now()
    experiments = _run_experiments(mission)
    selected = _selected_candidate(mission, experiments, out_dir)
    report = {
        "schema": RUN_SCHEMA,
        "mission": mission.name,
        "execution_mode": EXECUTION_MODE,
        "started_at": started_at,
        "finished_at": _utc_now(),
        "experiments": experiments,
        "selected_candidate": selected,
        "limitations": LIMITATIONS,
    }
    (out_dir / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


def _run_experiments(mission: Mission) -> list[dict[str, Any]]:
    experiments = [_run_one("baseline", mission.baseline, mission)]
    for candidate in mission.candidates:
        experiments.append(_run_one(candidate.id, candidate.program, mission))
    return experiments


def _run_one(candidate_id: str, program: ProgramRef, mission: Mission) -> dict[str, Any]:
    case_results = []
    for case in mission.cases:
        process = run_program(program.path, case.input, mission.timeout_seconds)
        case_results.append(evaluate_case(case.id, case.expected, process))
    return {
        "candidate_id": candidate_id,
        "source_sha256": sha256_file(program.path),
        "program": program.rel_path,
        "cases": case_results,
        "passed": experiment_passed(case_results),
    }


def _selected_candidate(
    mission: Mission, experiments: list[dict[str, Any]], out_dir: Path
) -> dict[str, Any] | None:
    candidate_by_id = {candidate.id: candidate for candidate in mission.candidates}
    for experiment in experiments:
        candidate_id = experiment["candidate_id"]
        if candidate_id == "baseline" or not experiment["passed"]:
            continue
        return _write_winner_bundle(mission, candidate_by_id[candidate_id], experiment, out_dir)
    return None


def _write_winner_bundle(
    mission: Mission, candidate: Candidate, experiment: dict[str, Any], out_dir: Path
) -> dict[str, Any]:
    winner_dir = out_dir / "winner"
    _replace_dir(winner_dir)
    shutil.copy2(candidate.program.path, winner_dir / "program.py")
    selected = {
        "id": candidate.id,
        "source_sha256": experiment["source_sha256"],
        "program": "program.py",
        "bundle_path": str(winner_dir),
        "unified_diff": unified_diff(
            mission.baseline.path,
            candidate.program.path,
            mission.baseline.rel_path,
            candidate.program.rel_path,
        ),
    }
    _write_manifest(winner_dir, mission.name, selected)
    return selected


def _write_manifest(winner_dir: Path, mission_name: str, selected: dict[str, Any]) -> None:
    manifest = {
        "schema": "rd-lab.winner/v1",
        "mission": mission_name,
        "candidate_id": selected["id"],
        "program": selected["program"],
        "source_sha256": selected["source_sha256"],
        "run": f"python {selected['program']}",
    }
    (winner_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")


def _prepare_output_dir(path: str | Path) -> Path:
    out_dir = Path(path).resolve()
    if out_dir.exists():
        raise ValidationError("output directory must not already exist")
    try:
        out_dir.mkdir(parents=True)
    except OSError as exc:
        raise ValidationError(f"could not create output directory: {out_dir}") from exc
    return out_dir


def _replace_dir(path: Path) -> None:
    if path.exists():
        raise ValidationError(f"winner directory already exists: {path}")
    path.mkdir(parents=True)


def _utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")
