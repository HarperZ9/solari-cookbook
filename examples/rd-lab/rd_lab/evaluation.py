import difflib
import hashlib
import json
from pathlib import Path
from typing import Any

from .execution import ProcessResult


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def evaluate_case(case_id: str, expected: Any, result: ProcessResult) -> dict[str, Any]:
    actual, parsed = _parse_stdout(result.stdout)
    if result.status == "timeout":
        status = "timeout"
    elif result.status == "output_too_large":
        status = "output_too_large"
    elif result.exit_code != 0:
        status = "nonzero_exit"
    elif not parsed:
        status = "invalid_json"
    elif not _json_literals_equal(actual, expected):
        status = "wrong_output"
    else:
        status = "passed"
    return {
        "id": case_id,
        "status": status,
        "expected": expected,
        "actual": actual,
        "exit_code": result.exit_code,
        "duration_ms": result.duration_ms,
    }


def experiment_passed(cases: list[dict[str, Any]]) -> bool:
    return bool(cases) and all(case["status"] == "passed" for case in cases)


def unified_diff(old_path: Path, new_path: Path, old_label: str, new_label: str) -> str:
    old_lines = old_path.read_text(encoding="utf-8").splitlines(keepends=True)
    new_lines = new_path.read_text(encoding="utf-8").splitlines(keepends=True)
    return "".join(
        difflib.unified_diff(old_lines, new_lines, fromfile=old_label, tofile=new_label)
    )


def _parse_stdout(stdout: str) -> tuple[Any, bool]:
    try:
        return json.loads(stdout, parse_constant=_reject_nonstandard_constant), True
    except (json.JSONDecodeError, ValueError):
        return None, False


def _json_literals_equal(actual: Any, expected: Any) -> bool:
    try:
        return _canonical_json(actual) == _canonical_json(expected)
    except (TypeError, ValueError):
        return False


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _reject_nonstandard_constant(value: str) -> None:
    raise ValueError(f"non-standard JSON constant: {value}")
