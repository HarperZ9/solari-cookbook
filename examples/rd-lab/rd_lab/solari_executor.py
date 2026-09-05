"""Optional Solari sandbox executor for synthetic R&D lab programs.

Importing this module does not import the Solari SDK. A cloud run starts only
after explicit upload authorization and an opened SDK-compatible client.
"""
from __future__ import annotations

import asyncio
import inspect
import time
import uuid
from typing import Any, Callable

from .solari_executor_support import (
    BOOTSTRAP_SOURCE,
    DEFAULT_BASE_URL,
    DEFAULT_COMMAND,
    DEFAULT_OUTPUT_LIMIT_BYTES,
    BoundedText,
    PreparedUpload,
    ProcessResult,
    SolariCleanupError,
    SolariUploadAuthorization,
    authorize_synthetic_upload,
    final_result,
    join,
    prepare_upload,
    result,
    sanitize_error,
    upload_manifest,
)


async def run_synthetic_program(
    program_source: str,
    case_input: Any,
    *,
    authorization: SolariUploadAuthorization | None = None,
    timeout_seconds: float,
    api_key: str | None = None,
    base_url: str = DEFAULT_BASE_URL,
    client_factory: Callable[[], Any] | None = None,
    command: str = DEFAULT_COMMAND,
    output_limit_bytes: int = DEFAULT_OUTPUT_LIMIT_BYTES,
) -> ProcessResult:
    started = time.perf_counter()
    prepared, denied = prepare_upload(program_source, case_input, authorization, started)
    if denied:
        return denied
    executor = SolariExecutor(
        api_key=api_key,
        base_url=base_url,
        client_factory=client_factory,
        command=command,
        output_limit_bytes=output_limit_bytes,
    )
    outcome = None
    try:
        async with executor:
            outcome = await executor.run_synthetic_program(
                program_source,
                case_input,
                authorization=prepared.authorization,
                timeout_seconds=timeout_seconds,
            )
            return outcome
    except SolariCleanupError as exc:
        if outcome is None:
            raise
        return result("cleanup_error", None, outcome.stdout, join(outcome.stderr, str(exc)), started)


class SolariExecutor:
    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str = DEFAULT_BASE_URL,
        client_factory: Callable[[], Any] | None = None,
        command: str = DEFAULT_COMMAND,
        template: str = "base",
        cpu: int = 1,
        mem_mb: int = 2048,
        sandbox_timeout_ms: int = 60_000,
        call_timeout_ms: int = 30_000,
        output_limit_bytes: int = DEFAULT_OUTPUT_LIMIT_BYTES,
        cleanup_timeout_seconds: float = 5,
    ) -> None:
        if output_limit_bytes <= 0:
            raise ValueError("output_limit_bytes must be positive")
        self._api_key = api_key
        self._base_url = base_url
        self._client_factory = client_factory
        self._command = command
        self._template = template
        self._cpu = cpu
        self._mem_mb = mem_mb
        self._sandbox_timeout_ms = sandbox_timeout_ms
        self._call_timeout_ms = call_timeout_ms
        self._output_limit_bytes = output_limit_bytes
        self._cleanup_timeout_seconds = cleanup_timeout_seconds
        self._client = None

    async def __aenter__(self) -> "SolariExecutor":
        self._client = await self._make_client()
        return self

    async def __aexit__(self, *_exc: Any) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        if self._client is None:
            return
        try:
            if hasattr(self._client, "aclose"):
                await self._client.aclose()
            elif hasattr(self._client, "close"):
                close_result = self._client.close()
                if inspect.isawaitable(close_result):
                    await close_result
        except Exception as exc:
            raise SolariCleanupError(f"client close failed: {sanitize_error(exc)}") from exc
        finally:
            self._client = None

    async def run_synthetic_program(
        self,
        program_source: str,
        case_input: Any,
        *,
        authorization: SolariUploadAuthorization | None,
        timeout_seconds: float,
    ) -> ProcessResult:
        started = time.perf_counter()
        prepared, denied = prepare_upload(program_source, case_input, authorization, started)
        if denied:
            return denied
        if timeout_seconds <= 0:
            return result("timeout", None, "", "wall deadline expired", started)
        return await self._execute(prepared, timeout_seconds, started)

    async def _make_client(self) -> Any:
        if self._client_factory is not None:
            client = self._client_factory()
            return await client if inspect.isawaitable(client) else client
        if not self._api_key:
            raise ValueError("SolariExecutor requires api_key or client_factory")
        from solari_sandbox.sandbox_client import SandboxClient

        return SandboxClient(
            api_key=self._api_key,
            base_url=self._base_url,
            call_timeout_ms=self._call_timeout_ms,
        )

    async def _execute(self, prepared: PreparedUpload, timeout: float, started: float) -> ProcessResult:
        deadline = started + timeout
        sandbox = None
        handle = None
        status = "cloud_error"
        exit_code = None
        stdout = BoundedText(self._output_limit_bytes)
        stderr = BoundedText(self._output_limit_bytes)
        error = ""
        try:
            sandbox = await self._create_sandbox(deadline)
            await _until(sandbox.connect(), deadline)
            work_dir = f"/tmp/rd-lab-{uuid.uuid4().hex}"
            await self._upload_bundle(sandbox, work_dir, prepared, deadline)
            handle = await self._start(sandbox, work_dir, deadline)
            status, exit_code = await self._wait(handle, stdout, stderr, deadline)
        except asyncio.TimeoutError:
            status, error = "timeout", "wall deadline expired"
        except _StartError as exc:
            status, error = "start_failed", f"start failed: {exc}"
        except Exception as exc:
            error = sanitize_error(exc)
        cleanup = await self._cleanup(sandbox, handle, status)
        return final_result(status, exit_code, stdout, stderr, error, cleanup, started)

    async def _create_sandbox(self, deadline: float) -> Any:
        return await _until(
            self._client.create(
                template=self._template,
                cpu=self._cpu,
                mem_mb=self._mem_mb,
                timeout_ms=self._sandbox_timeout_ms,
                lifecycle={"onTimeout": "kill"},
            ),
            deadline,
        )

    async def _upload_bundle(
        self,
        sandbox: Any,
        work_dir: str,
        prepared: PreparedUpload,
        deadline: float,
    ) -> None:
        await _until(sandbox.files.mkdir(work_dir), deadline)
        files = {
            f"{work_dir}/runner.py": BOOTSTRAP_SOURCE,
            f"{work_dir}/program.py": prepared.program_source,
            f"{work_dir}/input.json": prepared.input_json,
            f"{work_dir}/upload-manifest.json": upload_manifest(work_dir, prepared),
        }
        for path, data in files.items():
            await _until(sandbox.files.write(path, data), deadline)

    async def _start(self, sandbox: Any, work_dir: str, deadline: float) -> Any:
        try:
            return await _until(
                sandbox.commands.start(
                    self._command,
                    args=[f"{work_dir}/runner.py", f"{work_dir}/program.py", f"{work_dir}/input.json"],
                    cwd=work_dir,
                    env={"PYTHONIOENCODING": "utf-8", "PYTHONNOUSERSITE": "1"},
                    user=None,
                ),
                deadline,
            )
        except asyncio.TimeoutError:
            raise
        except Exception as exc:
            raise _StartError(sanitize_error(exc)) from exc

    async def _wait(
        self,
        handle: Any,
        stdout: BoundedText,
        stderr: BoundedText,
        deadline: float,
    ) -> tuple[str, int | None]:
        output_exceeded = asyncio.Event()

        def on_data(stream: str, data: str) -> None:
            target = stdout if stream == "stdout" else stderr
            if target.append(data):
                output_exceeded.set()

        handle.on_data(on_data)
        wait_task = asyncio.create_task(handle.wait())
        flood_task = asyncio.create_task(output_exceeded.wait())
        try:
            await asyncio.wait(
                {wait_task, flood_task},
                timeout=max(0, deadline - time.perf_counter()),
                return_when=asyncio.FIRST_COMPLETED,
            )
            if output_exceeded.is_set():
                if not wait_task.done():
                    await handle.kill()
                return "output_too_large", None
            if wait_task.done():
                return "ok", await wait_task
            await handle.kill()
            return "timeout", None
        finally:
            for task in (wait_task, flood_task):
                if not task.done():
                    task.cancel()

    async def _cleanup(self, sandbox: Any, handle: Any, status: str) -> list[str]:
        errors = []
        if handle is not None and status not in ("ok", "output_too_large", "timeout"):
            try:
                await _cleanup_call(handle.kill(), self._cleanup_timeout_seconds)
            except Exception as exc:
                errors.append(f"command kill failed: {sanitize_error(exc)}")
        if sandbox is None:
            return errors
        for label, call in (("sandbox kill", sandbox.kill), ("sandbox close", sandbox.close)):
            try:
                await _cleanup_call(call(), self._cleanup_timeout_seconds)
            except Exception as exc:
                errors.append(f"{label} failed: {sanitize_error(exc)}")
        return errors


class _StartError(RuntimeError):
    pass


async def _until(awaitable: Any, deadline: float) -> Any:
    remaining = deadline - time.perf_counter()
    if remaining <= 0:
        raise asyncio.TimeoutError
    return await asyncio.wait_for(awaitable, timeout=remaining)


async def _cleanup_call(awaitable: Any, timeout_seconds: float) -> Any:
    return await asyncio.wait_for(awaitable, timeout=timeout_seconds)
