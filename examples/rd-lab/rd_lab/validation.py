import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


MISSION_SCHEMA = "rd-lab.mission/v1"


class ValidationError(ValueError):
    pass


@dataclass(frozen=True)
class ProgramRef:
    rel_path: str
    path: Path


@dataclass(frozen=True)
class Candidate:
    id: str
    program: ProgramRef


@dataclass(frozen=True)
class Case:
    id: str
    input: Any
    expected: Any


@dataclass(frozen=True)
class Mission:
    name: str
    root: Path
    path: Path
    baseline: ProgramRef
    candidates: tuple[Candidate, ...]
    cases: tuple[Case, ...]
    timeout_seconds: float


def load_mission(path: str | Path) -> Mission:
    mission_path = Path(path)
    data = _read_json_object(mission_path)
    root = mission_path.parent.resolve(strict=True)
    if data.get("schema") != MISSION_SCHEMA:
        raise ValidationError(f"schema must be {MISSION_SCHEMA}")
    name = _required_string(data, "name")
    timeout_seconds = _read_timeout(data.get("timeout_seconds"))
    baseline = _program_ref(root, data.get("baseline"), "baseline")
    candidates = _read_candidates(root, data.get("candidates"))
    cases = _read_cases(data.get("cases"))
    return Mission(name, root, mission_path, baseline, candidates, cases, timeout_seconds)


def _read_json_object(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(
            path.read_text(encoding="utf-8"),
            parse_constant=_reject_nonstandard_constant,
        )
    except FileNotFoundError as exc:
        raise ValidationError(f"mission file not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ValidationError(f"mission JSON is invalid: {exc.msg}") from exc
    except ValueError as exc:
        raise ValidationError(f"mission JSON is invalid: {exc}") from exc
    if not isinstance(data, dict):
        raise ValidationError("mission JSON must be an object")
    return data


def _reject_nonstandard_constant(value: str) -> None:
    raise ValueError(f"non-standard JSON constant: {value}")


def _required_string(data: dict[str, Any], key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValidationError(f"{key} must be a non-empty string")
    return value


def _read_timeout(value: Any) -> float:
    if not isinstance(value, (int, float)) or isinstance(value, bool) or value <= 0:
        raise ValidationError("timeout_seconds must be a positive number")
    return float(value)


def _read_candidates(root: Path, value: Any) -> tuple[Candidate, ...]:
    if not isinstance(value, list) or not value:
        raise ValidationError("candidates must be a non-empty list")
    seen: set[str] = set()
    candidates = []
    for item in value:
        if not isinstance(item, dict):
            raise ValidationError("each candidate must be an object")
        candidate_id = _required_string(item, "id")
        if candidate_id == "baseline" or candidate_id in seen:
            raise ValidationError(f"duplicate candidate id: {candidate_id}")
        seen.add(candidate_id)
        candidates.append(Candidate(candidate_id, _program_ref(root, item.get("program"), candidate_id)))
    return tuple(candidates)


def _read_cases(value: Any) -> tuple[Case, ...]:
    if not isinstance(value, list) or not value:
        raise ValidationError("mission must include at least one case")
    seen: set[str] = set()
    cases = []
    for item in value:
        if not isinstance(item, dict):
            raise ValidationError("each case must be an object")
        case_id = _required_string(item, "id")
        if case_id in seen:
            raise ValidationError(f"duplicate case id: {case_id}")
        if "input" not in item or "expected" not in item:
            raise ValidationError(f"case {case_id} must include input and expected")
        seen.add(case_id)
        cases.append(Case(case_id, item["input"], item["expected"]))
    return tuple(cases)


def _program_ref(root: Path, value: Any, label: str) -> ProgramRef:
    if not isinstance(value, str) or not value:
        raise ValidationError(f"{label} program must be a relative path string")
    rel_path = Path(value)
    if rel_path.is_absolute() or ".." in rel_path.parts:
        raise ValidationError(f"{label} program must resolve within mission root")
    raw_path = root / rel_path
    _reject_symlink_parts(root, rel_path, label)
    try:
        resolved = raw_path.resolve(strict=True)
        resolved.relative_to(root)
    except (FileNotFoundError, ValueError) as exc:
        raise ValidationError(f"{label} program must resolve within mission root") from exc
    if not resolved.is_file():
        raise ValidationError(f"{label} program must be a file")
    return ProgramRef(value.replace("\\", "/"), resolved)


def _reject_symlink_parts(root: Path, rel_path: Path, label: str) -> None:
    current = root
    for part in rel_path.parts:
        current = current / part
        if current.exists() and current.is_symlink():
            raise ValidationError(f"{label} program path must not contain symlinks")
