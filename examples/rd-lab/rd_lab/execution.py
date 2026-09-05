import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any


MAX_OUTPUT_BYTES = 64 * 1024


@dataclass(frozen=True)
class ProcessResult:
    status: str
    exit_code: int | None
    stdout: str
    stderr: str
    duration_ms: int


def run_program(program_path: Path, case_input: Any, timeout_seconds: float) -> ProcessResult:
    with tempfile.TemporaryDirectory(prefix="rd-lab-run-") as tmp:
        run_dir = Path(tmp)
        copied_program = run_dir / "program.py"
        shutil.copy2(program_path, copied_program)
        return _run_copied_program(copied_program, case_input, timeout_seconds, run_dir)


def _run_copied_program(program_path: Path, case_input: Any, timeout: float, cwd: Path) -> ProcessResult:
    stdout_path = cwd / "stdout.bin"
    stderr_path = cwd / "stderr.bin"
    started = time.perf_counter()
    with tempfile.TemporaryFile() as stdin_file:
        stdin_file.write(json.dumps(case_input).encode("utf-8"))
        stdin_file.seek(0)
        return _launch_process(program_path, timeout, cwd, stdout_path, stderr_path, started, stdin_file)


def _launch_process(program_path: Path, timeout: float, cwd: Path, out: Path, err: Path, started: float, stdin_file):
    with out.open("wb") as stdout_file, err.open("wb") as stderr_file:
        proc = subprocess.Popen(
            [sys.executable, str(program_path)],
            cwd=cwd,
            env=_safe_env(),
            stdin=stdin_file,
            stdout=stdout_file,
            stderr=stderr_file,
        )
        status = _wait_for_process(proc, started, timeout, out, err)
        proc.wait(timeout=1)
    duration_ms = int((time.perf_counter() - started) * 1000)
    stdout = _read_text(out)
    stderr = _read_text(err)
    if status == "ok" and _files_too_large(out, err):
        status = "output_too_large"
    return ProcessResult(status, proc.returncode, stdout, stderr, duration_ms)


def _safe_env() -> dict[str, str]:
    env = {}
    for key in ("PATH", "SYSTEMROOT", "WINDIR", "COMSPEC", "PATHEXT", "TEMP", "TMP"):
        value = os.environ.get(key)
        if value:
            env[key] = value
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONNOUSERSITE"] = "1"
    return env


def _wait_for_process(proc: subprocess.Popen[bytes], started: float, timeout: float, out: Path, err: Path) -> str:
    deadline = started + timeout
    while proc.poll() is None:
        if time.perf_counter() >= deadline:
            _kill_process(proc)
            return "timeout"
        if _files_too_large(out, err):
            _kill_process(proc)
            return "output_too_large"
        time.sleep(0.01)
    return "ok"


def _kill_process(proc: subprocess.Popen[bytes]) -> None:
    proc.kill()
    try:
        proc.wait(timeout=1)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=1)


def _files_too_large(*paths: Path) -> bool:
    return any(path.exists() and path.stat().st_size > MAX_OUTPUT_BYTES for path in paths)


def _read_text(path: Path) -> str:
    with path.open("rb") as handle:
        data = handle.read(MAX_OUTPUT_BYTES)
    return data.decode("utf-8", errors="replace")
