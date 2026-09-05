import asyncio
import inspect
import json
import os
import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class ImportBoundaryTests(unittest.TestCase):
    def test_importing_executor_does_not_import_solari_sdk(self):
        env = {}
        for key in ("PATH", "SYSTEMROOT", "WINDIR", "COMSPEC", "PATHEXT", "TEMP", "TMP"):
            if os.environ.get(key):
                env[key] = os.environ[key]
        env["PYTHONPATH"] = str(ROOT)
        env["PYTHONIOENCODING"] = "utf-8"
        probe = (
            "import sys; "
            "import rd_lab.solari_executor; "
            "print(any(name.startswith('solari_') for name in sys.modules))"
        )

        result = subprocess.run(
            [sys.executable, "-c", probe],
            cwd=ROOT,
            env=env,
            text=True,
            capture_output=True,
            timeout=5,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "False")


class FakeClient:
    def __init__(self, sandbox=None, *, create_error=None, close_error=None):
        self.sandbox = sandbox or FakeSandbox()
        self.create_error = create_error
        self.close_error = close_error
        self.create_calls = []
        self.closed = False

    async def create(self, **kwargs):
        self.create_calls.append(kwargs)
        if self.create_error:
            raise self.create_error
        return self.sandbox

    async def aclose(self):
        self.closed = True
        if self.close_error:
            raise self.close_error


class FakeSandbox:
    def __init__(self, handle=None, *, connect_error=None, kill_error=None, close_error=None):
        self.files = FakeFiles()
        self.commands = FakeCommands(handle or FakeCommandHandle())
        self.connect_error = connect_error
        self.kill_error = kill_error
        self.close_error = close_error
        self.connected = False
        self.kill_calls = 0
        self.close_calls = 0

    async def connect(self):
        if self.connect_error:
            raise self.connect_error
        self.connected = True

    async def kill(self):
        self.kill_calls += 1
        if self.kill_error:
            raise self.kill_error

    async def close(self):
        self.close_calls += 1
        if self.close_error:
            raise self.close_error


class FakeFiles:
    def __init__(self):
        self.mkdirs = []
        self.writes = {}

    async def mkdir(self, path):
        self.mkdirs.append(path)

    async def write(self, path, data):
        self.writes[path] = data


class FakeCommands:
    def __init__(self, handle=None, *, start_error=None):
        self.handle = handle or FakeCommandHandle()
        self.start_error = start_error
        self.start_calls = []

    async def start(self, cmd, *, args=None, cwd=None, env=None, user=None):
        self.start_calls.append({"cmd": cmd, "args": args, "cwd": cwd, "env": env, "user": user})
        if self.start_error:
            raise self.start_error
        return self.handle


class FakeCommandHandle:
    def __init__(self, *, exit_code=0, frames=None, wait_forever=False, wait_delay=0):
        self.exit_code = exit_code
        self.frames = frames or []
        self.wait_forever = wait_forever
        self.wait_delay = wait_delay
        self.callbacks = []
        self.kill_calls = []

    def on_data(self, callback):
        self.callbacks.append(callback)

    async def wait(self):
        for stream, data in self.frames:
            for callback in self.callbacks:
                callback(stream, data)
        if self.wait_forever:
            await asyncio.Event().wait()
        if self.wait_delay:
            await asyncio.sleep(self.wait_delay)
        return self.exit_code

    async def kill(self, signal=None):
        self.kill_calls.append(signal)


class SolariExecutorTests(unittest.IsolatedAsyncioTestCase):
    async def test_missing_upload_authorization_fails_closed_before_client_creation(self):
        from rd_lab.solari_executor import run_synthetic_program

        client_calls = []

        async def client_factory():
            client_calls.append("created")
            return FakeClient()

        result = await run_synthetic_program(
            "print('not run')",
            {"value": 1},
            client_factory=client_factory,
            timeout_seconds=1,
        )

        self.assertEqual(result.status, "upload_denied")
        self.assertIsNone(result.exit_code)
        self.assertIn("explicit upload authorization", result.stderr)
        self.assertEqual(client_calls, [])

    async def test_authorization_mismatch_is_rejected_before_upload(self):
        from rd_lab.solari_executor import SolariExecutor, authorize_synthetic_upload

        program = "import json, sys\nprint(json.dumps(json.load(sys.stdin)))"
        authorization = authorize_synthetic_upload(program, {"value": 1})
        client = FakeClient()

        async with SolariExecutor(client_factory=lambda: client) as executor:
            result = await executor.run_synthetic_program(
                program + "\n# changed after approval",
                {"value": 1},
                authorization=authorization,
                timeout_seconds=1,
            )

        self.assertEqual(result.status, "upload_denied")
        self.assertIsNone(result.exit_code)
        self.assertEqual(client.create_calls, [])
        self.assertEqual(client.sandbox.files.writes, {})

    async def test_success_uploads_only_program_input_manifest_and_bootstrap(self):
        from rd_lab.solari_executor import SolariExecutor, authorize_synthetic_upload

        program = "import json, sys\nprint(json.dumps(json.load(sys.stdin)))"
        case_input = {"visible": "candidate-input"}
        authorization = authorize_synthetic_upload(program, case_input)
        handle = FakeCommandHandle(exit_code=0, frames=[("stdout", '{"ok": true}\n')])
        sandbox = FakeSandbox(handle)
        client = FakeClient(sandbox)

        async with SolariExecutor(client_factory=lambda: client, command="python3") as executor:
            result = await executor.run_synthetic_program(
                program,
                case_input,
                authorization=authorization,
                timeout_seconds=1,
            )

        self.assertEqual(result.status, "ok", result.stderr)
        self.assertEqual(result.exit_code, 0)
        self.assertEqual(result.stdout, '{"ok": true}\n')
        self.assertEqual(result.stderr, "")
        self.assertTrue(sandbox.connected)
        self.assertEqual(sandbox.kill_calls, 1)
        self.assertEqual(sandbox.close_calls, 1)
        self.assertTrue(client.closed)
        self.assertEqual(client.create_calls[0]["lifecycle"], {"onTimeout": "kill"})

        work_dir = sandbox.files.mkdirs[0]
        start = sandbox.commands.start_calls[0]
        self.assertEqual(start["cmd"], "python3")
        self.assertEqual(start["cwd"], work_dir)
        self.assertEqual(start["user"], None)
        self.assertEqual(
            start["args"],
            [f"{work_dir}/runner.py", f"{work_dir}/program.py", f"{work_dir}/input.json"],
        )
        self.assertNotIn("expected", inspect.signature(executor.run_synthetic_program).parameters)

        uploads = sandbox.files.writes
        self.assertEqual(
            set(uploads),
            {
                f"{work_dir}/runner.py",
                f"{work_dir}/program.py",
                f"{work_dir}/input.json",
                f"{work_dir}/upload-manifest.json",
            },
        )
        runner = uploads[f"{work_dir}/runner.py"]
        self.assertIn("sys.stdin = input_handle", runner)
        self.assertIn("runpy.run_path(program_path, run_name=\"__main__\")", runner)
        self.assertEqual(uploads[f"{work_dir}/program.py"], program)
        self.assertEqual(json.loads(uploads[f"{work_dir}/input.json"]), case_input)
        uploaded_blob = "\n".join(str(value) for value in uploads.values())
        self.assertNotIn("oracle-secret", uploaded_blob)
        self.assertNotIn("expected", uploaded_blob)

    async def test_timeout_kills_command_and_sandbox(self):
        from rd_lab.solari_executor import SolariExecutor, authorize_synthetic_upload

        program = "import time\ntime.sleep(3600)"
        authorization = authorize_synthetic_upload(program, {})
        handle = FakeCommandHandle(wait_forever=True)
        sandbox = FakeSandbox(handle)
        client = FakeClient(sandbox)

        async with SolariExecutor(client_factory=lambda: client) as executor:
            result = await executor.run_synthetic_program(
                program,
                {},
                authorization=authorization,
                timeout_seconds=0.01,
            )

        self.assertEqual(result.status, "timeout")
        self.assertIsNone(result.exit_code)
        self.assertEqual(handle.kill_calls, [None])
        self.assertEqual(sandbox.kill_calls, 1)
        self.assertEqual(sandbox.close_calls, 1)

    async def test_output_flood_is_byte_bounded_and_killed(self):
        from rd_lab.solari_executor import SolariExecutor, authorize_synthetic_upload

        program = "print('x')"
        authorization = authorize_synthetic_upload(program, {})
        handle = FakeCommandHandle(frames=[("stdout", "abcdef")], wait_forever=True)
        sandbox = FakeSandbox(handle)
        client = FakeClient(sandbox)

        async with SolariExecutor(client_factory=lambda: client, output_limit_bytes=4) as executor:
            result = await executor.run_synthetic_program(
                program,
                {},
                authorization=authorization,
                timeout_seconds=1,
            )

        self.assertEqual(result.status, "output_too_large")
        self.assertIsNone(result.exit_code)
        self.assertEqual(result.stdout, "abcd")
        self.assertEqual(handle.kill_calls, [None])

    async def test_start_failure_cleans_sandbox_and_sanitizes_error(self):
        from rd_lab.solari_executor import SolariExecutor, authorize_synthetic_upload

        program = "print('x')"
        authorization = authorize_synthetic_upload(program, {})
        secret_error = RuntimeError("failed https://example.test?pt_token=secret sandbox_abc123")
        sandbox = FakeSandbox()
        sandbox.commands = FakeCommands(start_error=secret_error)
        client = FakeClient(sandbox)

        async with SolariExecutor(client_factory=lambda: client) as executor:
            result = await executor.run_synthetic_program(
                program,
                {},
                authorization=authorization,
                timeout_seconds=1,
            )

        self.assertEqual(result.status, "start_failed")
        self.assertIsNone(result.exit_code)
        self.assertIn("start failed", result.stderr)
        self.assertNotIn("pt_token=secret", result.stderr)
        self.assertNotIn("sandbox_abc123", result.stderr)
        self.assertEqual(sandbox.kill_calls, 1)
        self.assertEqual(sandbox.close_calls, 1)

    async def test_cleanup_error_is_returned_not_silent(self):
        from rd_lab.solari_executor import SolariExecutor, authorize_synthetic_upload

        program = "print('x')"
        authorization = authorize_synthetic_upload(program, {})
        handle = FakeCommandHandle(exit_code=0, frames=[("stdout", "{}")])
        sandbox = FakeSandbox(
            handle,
            kill_error=RuntimeError("kill leaked sandbox_deadbeef"),
            close_error=RuntimeError("close leaked https://example.test/path?pt_token=hidden"),
        )
        client = FakeClient(sandbox)

        async with SolariExecutor(client_factory=lambda: client) as executor:
            result = await executor.run_synthetic_program(
                program,
                {},
                authorization=authorization,
                timeout_seconds=1,
            )

        self.assertEqual(result.status, "cleanup_error")
        self.assertIsNone(result.exit_code)
        self.assertIn("sandbox kill failed", result.stderr)
        self.assertIn("sandbox close failed", result.stderr)
        self.assertNotIn("sandbox_deadbeef", result.stderr)
        self.assertNotIn("pt_token=hidden", result.stderr)


if __name__ == "__main__":
    unittest.main()
