import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from rd_lab.execution import MAX_OUTPUT_BYTES, _read_text
from tests.helpers import (
    load_report,
    run_lab,
    simple_mission,
    visibility_mission,
    write_json,
    write_program,
    wrong_output_mission,
)


class GuardedOutputPath:
    def __init__(self):
        self.handle = GuardedOutputHandle()

    def open(self, mode):
        self.handle.mode = mode
        return self.handle

    def read_bytes(self):
        raise AssertionError("output preview used an unbounded read")


class GuardedOutputHandle:
    def __init__(self):
        self.mode = None
        self.read_sizes = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def read(self, size=-1):
        self.read_sizes.append(size)
        return b"x" * min(size, MAX_OUTPUT_BYTES + 1024)


class ExecutionContractTests(unittest.TestCase):
    def test_large_input_to_nonreading_candidate_respects_case_timeout(self):
        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp)
            mission_root = work / "mission"
            mission_root.mkdir()
            large_payload = "x" * (2 * 1024 * 1024)
            write_program(mission_root / "baseline.py", "import json; print(json.dumps({}))")
            write_program(mission_root / "sleeper.py", "import time\ntime.sleep(5)\nprint('{}')")
            write_json(
                mission_root / "mission.json",
                {
                    "schema": "rd-lab.mission/v1",
                    "name": "large-input-timeout",
                    "baseline": "baseline.py",
                    "candidates": [{"id": "sleeper", "program": "sleeper.py"}],
                    "cases": [{"id": "large", "input": {"blob": large_payload}, "expected": {}}],
                    "timeout_seconds": 0.5,
                },
            )

            try:
                result = run_lab(mission_root / "mission.json", work / "out", timeout=3)
            except subprocess.TimeoutExpired as exc:
                self.fail(f"engine did not honor timeout with large stdin: {exc}")

            self.assertEqual(result.returncode, 0, result.stderr)
            report = load_report(work / "out")
            sleeper = next(exp for exp in report["experiments"] if exp["candidate_id"] == "sleeper")
            self.assertEqual(sleeper["cases"][0]["status"], "timeout")

    def test_output_preview_reads_only_the_configured_bound(self):
        guarded = GuardedOutputPath()

        text = _read_text(guarded)

        self.assertEqual(len(text), MAX_OUTPUT_BYTES)
        self.assertEqual(guarded.handle.mode, "rb")
        self.assertEqual(guarded.handle.read_sizes, [MAX_OUTPUT_BYTES])

    def test_preexisting_output_directory_is_rejected_before_running_candidates(self):
        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp)
            mission_root = work / "mission"
            mission_root.mkdir()
            sentinel = work / "candidate-ran.txt"
            out = work / "out"
            (out / "winner").mkdir(parents=True)
            protected = out / "winner" / "protected.txt"
            protected.write_text("keep", encoding="utf-8")
            write_program(mission_root / "baseline.py", "import json; print(json.dumps({}))")
            write_program(
                mission_root / "writer.py",
                """
                import json
                import pathlib
                import sys
                payload = json.load(sys.stdin)
                pathlib.Path(payload["sentinel"]).write_text("ran", encoding="utf-8")
                print(json.dumps({}))
                """,
            )
            write_json(
                mission_root / "mission.json",
                {
                    "schema": "rd-lab.mission/v1",
                    "name": "preexisting-output",
                    "baseline": "baseline.py",
                    "candidates": [{"id": "writer", "program": "writer.py"}],
                    "cases": [{"id": "one", "input": {"sentinel": str(sentinel)}, "expected": {}}],
                    "timeout_seconds": 1,
                },
            )

            result = run_lab(mission_root / "mission.json", out)

            self.assertEqual(result.returncode, 2)
            self.assertIn("output directory must not already exist", result.stderr)
            self.assertFalse(sentinel.exists())
            self.assertEqual(protected.read_text(encoding="utf-8"), "keep")
            self.assertFalse((out / "report.json").exists())

    def test_bool_and_number_are_not_equal_in_oracle_comparison(self):
        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp)
            mission_root = work / "mission"
            mission_root.mkdir()
            write_program(mission_root / "baseline.py", "import json; print(json.dumps({'ok': 0}))")
            write_program(mission_root / "truthy.py", "import json; print(json.dumps({'ok': 1}))")
            write_json(
                mission_root / "mission.json",
                {
                    "schema": "rd-lab.mission/v1",
                    "name": "bool-number",
                    "baseline": "baseline.py",
                    "candidates": [{"id": "truthy", "program": "truthy.py"}],
                    "cases": [{"id": "one", "input": {}, "expected": {"ok": True}}],
                    "timeout_seconds": 1,
                },
            )

            result = run_lab(mission_root / "mission.json", work / "out")

            self.assertEqual(result.returncode, 0, result.stderr)
            report = load_report(work / "out")
            truthy = next(exp for exp in report["experiments"] if exp["candidate_id"] == "truthy")
            self.assertEqual(truthy["cases"][0]["status"], "wrong_output")
            self.assertIsNone(report["selected_candidate"])

    def test_candidate_stdout_rejects_nonstandard_nan(self):
        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp)
            mission_root = work / "mission"
            mission_root.mkdir()
            write_program(mission_root / "baseline.py", "import json; print(json.dumps({'value': 0}))")
            write_program(mission_root / "nan.py", "print('NaN')")
            write_json(
                mission_root / "mission.json",
                {
                    "schema": "rd-lab.mission/v1",
                    "name": "nan-output",
                    "baseline": "baseline.py",
                    "candidates": [{"id": "nan", "program": "nan.py"}],
                    "cases": [{"id": "one", "input": {}, "expected": {"value": 0}}],
                    "timeout_seconds": 1,
                },
            )

            result = run_lab(mission_root / "mission.json", work / "out")

            self.assertEqual(result.returncode, 0, result.stderr)
            report = load_report(work / "out")
            nan = next(exp for exp in report["experiments"] if exp["candidate_id"] == "nan")
            self.assertEqual(nan["cases"][0]["status"], "invalid_json")
            self.assertIsNone(report["selected_candidate"])

    def test_wrong_output_with_zero_exit_is_failed_without_selecting_candidate(self):
        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp)
            mission_root = wrong_output_mission(work)

            result = run_lab(mission_root / "mission.json", work / "out")

            self.assertEqual(result.returncode, 0, result.stderr)
            report = load_report(work / "out")
            self.assertEqual(report["schema"], "rd-lab.run/v1")
            self.assertEqual(report["execution_mode"], "local_trusted_subprocess")
            self.assertIsNone(report["selected_candidate"])
            wrong = next(exp for exp in report["experiments"] if exp["candidate_id"] == "wrong")
            self.assertFalse(wrong["passed"])
            self.assertEqual(wrong["cases"][0]["status"], "wrong_output")
            self.assertEqual(wrong["cases"][0]["expected"], {"value": "expected"})
            self.assertEqual(wrong["cases"][0]["actual"], {"value": "wrong"})
            self.assertEqual(wrong["cases"][0]["exit_code"], 0)

    def test_timeout_invalid_json_and_nonzero_exit_have_distinct_statuses(self):
        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp)
            mission_root = work / "mission"
            mission_root.mkdir()
            write_program(mission_root / "baseline.py", "import json; print(json.dumps({}))")
            write_program(mission_root / "timeout.py", "import time\nwhile True:\n    time.sleep(1)")
            write_program(mission_root / "invalid.py", "print('{not json')")
            write_program(mission_root / "nonzero.py", "import sys\nprint('{\"ok\": true}')\nsys.exit(7)")
            write_json(
                mission_root / "mission.json",
                {
                    "schema": "rd-lab.mission/v1",
                    "name": "distinct-failures",
                    "baseline": "baseline.py",
                    "candidates": [
                        {"id": "timeout", "program": "timeout.py"},
                        {"id": "invalid", "program": "invalid.py"},
                        {"id": "nonzero", "program": "nonzero.py"},
                    ],
                    "cases": [{"id": "one", "input": {}, "expected": {"ok": True}}],
                    "timeout_seconds": 3,
                },
            )

            result = run_lab(mission_root / "mission.json", work / "out")

            self.assertEqual(result.returncode, 0, result.stderr)
            report = load_report(work / "out")
            statuses = {exp["candidate_id"]: exp["cases"][0]["status"] for exp in report["experiments"]}
            self.assertEqual(statuses["timeout"], "timeout")
            self.assertEqual(statuses["invalid"], "invalid_json")
            self.assertEqual(statuses["nonzero"], "nonzero_exit")
            self.assertIsNone(report["selected_candidate"])

    def test_candidate_cannot_see_expected_values_in_stdin_or_work_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp)
            mission_root = visibility_mission(work)

            result = run_lab(mission_root / "mission.json", work / "out")

            self.assertEqual(result.returncode, 0, result.stderr)
            report = load_report(work / "out")
            snoop = next(exp for exp in report["experiments"] if exp["candidate_id"] == "snoop")
            self.assertEqual(snoop["cases"][0]["status"], "wrong_output")
            self.assertEqual(snoop["cases"][0]["actual"], {"leaked": False})
            self.assertIsNone(report["selected_candidate"])

    def test_second_arbitrary_mission_selects_repair_and_writes_runnable_bundle(self):
        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp)
            mission_root = simple_mission(work)
            write_program(
                mission_root / "fixed.py",
                """
                import json
                import sys
                payload = json.load(sys.stdin)
                print(json.dumps({"value": payload["value"] * 2}))
                """,
            )
            write_json(
                mission_root / "mission.json",
                {
                    "schema": "rd-lab.mission/v1",
                    "name": "double-number",
                    "baseline": "baseline.py",
                    "candidates": [{"id": "fixed", "program": "fixed.py"}],
                    "cases": [{"id": "double", "input": {"value": 3}, "expected": {"value": 6}}],
                    "timeout_seconds": 1,
                },
            )
            original = (mission_root / "fixed.py").read_bytes()

            result = run_lab(mission_root / "mission.json", work / "out")

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual((mission_root / "fixed.py").read_bytes(), original)
            report = load_report(work / "out")
            self.assertEqual(report["selected_candidate"]["id"], "fixed")
            self.assertIn("--- baseline.py", report["selected_candidate"]["unified_diff"])
            self.assertIn("+++ fixed.py", report["selected_candidate"]["unified_diff"])
            bundle_program = Path(report["selected_candidate"]["bundle_path"]) / "program.py"
            self.assertTrue(bundle_program.exists())
            probe = subprocess.run(
                [sys.executable, str(bundle_program)],
                input=json.dumps({"value": 5}),
                text=True,
                capture_output=True,
                timeout=5,
            )
            self.assertEqual(probe.returncode, 0, probe.stderr)
            self.assertEqual(json.loads(probe.stdout), {"value": 10})


if __name__ == "__main__":
    unittest.main()
