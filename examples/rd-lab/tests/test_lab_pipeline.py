import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


class LabPipelineTests(unittest.TestCase):
    def run_cli(self, *args):
        return subprocess.run([sys.executable, "-m", "rd_lab", *args],
                              capture_output=True, text=True, timeout=30)

    def test_run_produces_offline_view_with_actual_case_results(self):
        with tempfile.TemporaryDirectory() as temporary:
            out = Path(temporary) / "run"
            result = self.run_cli("run", "fixtures/csv-importer/mission.json", "--out", str(out))
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue((out / "index.html").is_file(), "Run must leave a navigable result")
            html = (out / "index.html").read_text(encoding="utf-8")
            self.assertIn("4 / 4", html)
            self.assertIn("Wrong output", html)

    @unittest.skipUnless(importlib.util.find_spec("index_graph"), "Optional Index package not installed")
    def test_index_inspection_is_in_the_saved_report_and_view(self):
        with tempfile.TemporaryDirectory() as temporary:
            out = Path(temporary) / "run"
            result = self.run_cli("run", "fixtures/csv-importer/mission.json", "--out", str(out),
                                  "--inspect-symbol", "parse_rows")
            self.assertEqual(result.returncode, 0, result.stderr)
            report = json.loads((out / "report.json").read_text(encoding="utf-8"))
            self.assertEqual(report["source_inspection"]["definitions"][0]["name"], "parse_rows")
            html = (out / "index.html").read_text(encoding="utf-8")
            self.assertIn("Source investigation", html)
            self.assertIn("candidates/repair.py:23", html)
            self.assertIn("Static source navigation", html)


if __name__ == "__main__":
    unittest.main()
