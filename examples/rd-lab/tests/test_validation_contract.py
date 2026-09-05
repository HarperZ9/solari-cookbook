import tempfile
import unittest
from pathlib import Path

from tests.helpers import run_lab, simple_mission, write_json, write_program


class ValidationContractTests(unittest.TestCase):
    def test_mission_with_no_cases_is_rejected_instead_of_vacuously_passing(self):
        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp)
            candidate = {"id": "fixed", "program": "fixed.py"}
            mission_root = simple_mission(work, cases=[], candidates=[candidate])
            write_program(mission_root / "fixed.py", "import json; print(json.dumps({}))")

            result = run_lab(mission_root / "mission.json", work / "out")

            self.assertEqual(result.returncode, 2)
            self.assertIn("at least one case", result.stderr)
            self.assertFalse((work / "out" / "report.json").exists())

    def test_rejects_traversal_paths_and_duplicate_ids(self):
        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp)
            mission_root = work / "mission"
            mission_root.mkdir()
            write_program(work / "escape.py", "print('{}')")
            write_program(mission_root / "baseline.py", "print('{}')")
            write_program(mission_root / "candidate.py", "print('{}')")
            base = {
                "schema": "rd-lab.mission/v1",
                "name": "invalid-paths",
                "baseline": "baseline.py",
                "cases": [{"id": "one", "input": {}, "expected": {}}],
                "timeout_seconds": 1,
            }
            write_json(
                mission_root / "mission.json",
                {**base, "candidates": [{"id": "escape", "program": "../escape.py"}]},
            )

            traversal = run_lab(mission_root / "mission.json", work / "out-traversal")

            self.assertEqual(traversal.returncode, 2)
            self.assertIn("within mission root", traversal.stderr)

            write_json(
                mission_root / "mission.json",
                {
                    **base,
                    "candidates": [
                        {"id": "same", "program": "candidate.py"},
                        {"id": "same", "program": "candidate.py"},
                    ],
                },
            )

            duplicate = run_lab(mission_root / "mission.json", work / "out-duplicate")

            self.assertEqual(duplicate.returncode, 2)
            self.assertIn("duplicate candidate id", duplicate.stderr)

    def test_rejects_nonstandard_nan_in_mission_oracle(self):
        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp)
            mission_root = work / "mission"
            mission_root.mkdir()
            write_program(mission_root / "baseline.py", "print('{}')")
            write_program(mission_root / "candidate.py", "print('{}')")
            (mission_root / "mission.json").write_text(
                """
                {
                  "schema": "rd-lab.mission/v1",
                  "name": "nan-oracle",
                  "baseline": "baseline.py",
                  "candidates": [{"id": "candidate", "program": "candidate.py"}],
                  "cases": [{"id": "one", "input": {}, "expected": NaN}],
                  "timeout_seconds": 1
                }
                """,
                encoding="utf-8",
            )

            result = run_lab(mission_root / "mission.json", work / "out")

            self.assertEqual(result.returncode, 2)
            self.assertIn("non-standard JSON constant", result.stderr)


if __name__ == "__main__":
    unittest.main()
