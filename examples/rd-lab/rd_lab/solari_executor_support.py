from __future__ import annotations

import hashlib
import json
import re
import time
from dataclasses import dataclass
from typing import Any


DEFAULT_BASE_URL = "https://api.getsolari.com"
DEFAULT_COMMAND = "python3"
DEFAULT_OUTPUT_LIMIT_BYTES = 64 * 1024
DEFAULT_PURPOSE = "rd-lab synthetic program execution"

BOOTSTRAP_SOURCE = """\
import runpy
import sys

program_path = sys.argv[1]
input_path = sys.argv[2]

with open(input_path, "r", encoding="utf-8") as input_handle:
    sys.stdin = input_handle
    sys.argv = [program_path]
    runpy.run_path(program_path, run_name="__main__")
"""


@dataclass(frozen=True)
class ProcessResult:
    status: str
    exit_code: int | None
    stdout: str
    stderr: str
    duration_ms: int


@dataclass(frozen=True)
class SolariUploadAuthorization:
    program_sha256: str
    input_sha256: str
    purpose: str = DEFAULT_PURPOSE
    synthetic_only: bool = True


@dataclass(frozen=True)
class PreparedUpload:
    program_source: str
    input_json: str
    program_sha256: str
    input_sha256: str
    authorization: SolariUploadAuthorization


class SolariCleanupError(RuntimeError):
    pass


class BoundedText:
    def __init__(self, limit: int) -> None:
        self._limit = limit
        self._size = 0
        self._chunks: list[bytes] = []
        self.exceeded = False

    def append(self, data: str) -> bool:
        raw = data.encode("utf-8", errors="replace")
        remaining = self._limit - self._size
        if remaining > 0:
            chunk = raw[:remaining]
            self._chunks.append(chunk)
            self._size += len(chunk)
        if len(raw) > remaining:
            self.exceeded = True
        return self.exceeded

    def text(self) -> str:
        return b"".join(self._chunks).decode("utf-8", errors="replace")


def authorize_synthetic_upload(
    program_source: str,
    case_input: Any,
    *,
    purpose: str = DEFAULT_PURPOSE,
) -> SolariUploadAuthorization:
    input_json = json_input(case_input)
    return SolariUploadAuthorization(
        sha256_text(program_source),
        sha256_text(input_json),
        purpose,
    )


def prepare_upload(
    program_source: str,
    case_input: Any,
    authorization: SolariUploadAuthorization | None,
    started: float,
) -> tuple[PreparedUpload, None] | tuple[None, ProcessResult]:
    if authorization is None:
        return None, result("upload_denied", None, "", "explicit upload authorization is required", started)
    try:
        input_json = json_input(case_input)
    except (TypeError, ValueError) as exc:
        return None, result("upload_denied", None, "", f"input is not strict JSON: {exc}", started)
    program_sha = sha256_text(program_source)
    input_sha = sha256_text(input_json)
    if not authorization.synthetic_only:
        return None, result("upload_denied", None, "", "authorization must be synthetic-only", started)
    if authorization.program_sha256 != program_sha or authorization.input_sha256 != input_sha:
        return None, result("upload_denied", None, "", "upload authorization hash mismatch", started)
    return PreparedUpload(program_source, input_json, program_sha, input_sha, authorization), None


def upload_manifest(work_dir: str, prepared: PreparedUpload) -> str:
    manifest = {
        "schema": "rd-lab.solari-upload/v1",
        "purpose": prepared.authorization.purpose,
        "synthetic_only": prepared.authorization.synthetic_only,
        "program": {"path": f"{work_dir}/program.py", "sha256": prepared.program_sha256},
        "input": {"path": f"{work_dir}/input.json", "sha256": prepared.input_sha256},
        "bootstrap": {"path": f"{work_dir}/runner.py"},
    }
    return json.dumps(manifest, sort_keys=True, separators=(",", ":"), allow_nan=False)


def json_input(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":"))


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def final_result(
    status: str,
    exit_code: int | None,
    stdout: BoundedText,
    stderr: BoundedText,
    error: str,
    cleanup_errors: list[str],
    started: float,
) -> ProcessResult:
    if cleanup_errors:
        status = "cleanup_error"
        exit_code = None
    return result(status, exit_code, stdout.text(), join(stderr.text(), error, *cleanup_errors), started)


def join(*parts: str) -> str:
    return "\n".join(part for part in parts if part)


def result(status: str, exit_code: int | None, stdout: str, stderr: str, started: float) -> ProcessResult:
    return ProcessResult(status, exit_code, stdout, stderr, int((time.perf_counter() - started) * 1000))


def sanitize_error(exc: BaseException) -> str:
    text = str(exc) or exc.__class__.__name__
    text = re.sub(r"https?://\S+", "[redacted-url]", text)
    text = re.sub(r"\b(?:sandbox|session|sess|cmd|sbx)_[A-Za-z0-9._-]+\b", "[redacted-id]", text)
    return re.sub(r"(?i)(pt_token|api[_-]?key|token)=\S+", r"\1=[redacted]", text)
