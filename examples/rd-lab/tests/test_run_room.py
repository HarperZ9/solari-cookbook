"""Behavioral checks for the offline, evidence-led report view."""
import copy
import importlib.util
import unittest


class RunRoomTests(unittest.TestCase):
    def render(self, report):
        self.assertIsNotNone(importlib.util.find_spec("rd_lab.run_room"),
                             "The offline run-room renderer has not been built")
        from rd_lab.run_room import render_report
        return render_report(report)

    def report(self):
        case = {"id": "locale", "status": "passed", "expected": [1],
                "actual": [1], "exit_code": 0, "duration_ms": 12}
        experiments = [
            {"candidate_id": "baseline", "source_sha256": "a" * 64,
             "passed": False, "cases": [{**case, "status": "wrong_output",
                                          "actual": []}]},
            {"candidate_id": "repair", "source_sha256": "b" * 64,
             "passed": True, "cases": [case]},
        ]
        return {"schema": "rd-lab.run/v1", "mission": "CSV importer",
                "execution_mode": "local_trusted_subprocess",
                "started_at": "2026-09-05T01:00:00Z",
                "finished_at": "2026-09-05T01:00:01Z",
                "experiments": experiments,
                "selected_candidate": {"id": "repair", "source_sha256": "b" * 64,
                                       "bundle_path": "C:/private/do-not-render",
                                       "unified_diff": "- broken\n+ repaired"},
                "limitations": ["Fixture candidates, not model-generated repairs."]}

    def test_view_contains_outcomes_diff_and_boundaries_without_javascript(self):
        html = self.render(self.report())
        for text in ("CSV importer", "0 / 1", "1 / 1", "Wrong output",
                     "- broken", "+ repaired", "not a security sandbox",
                     "Fixture candidates, not model-generated repairs.",
                     '<main id="main"', "<summary", "prefers-reduced-motion",
                     "forced-colors", "@media print"):
            self.assertIn(text, html)
        self.assertNotIn("<script", html)
        self.assertNotIn("C:/private", html)
        self.assertNotIn("https://", html)

    def test_all_displayed_report_content_is_escaped(self):
        report = self.report()
        payload = '<img src=x onerror="alert(1)">'
        report["mission"] = payload
        report["experiments"][0]["cases"][0]["actual"] = payload
        report["selected_candidate"]["unified_diff"] = payload
        report["limitations"] = [payload]
        html = self.render(report)
        self.assertNotIn("<img", html)
        self.assertIn("&lt;img", html)

    def test_does_not_present_unearned_selection(self):
        for mutation in ("failed", "empty", "baseline", "hash"):
            report = self.report()
            if mutation == "failed":
                report["experiments"][1]["cases"][0]["status"] = "wrong_output"
            elif mutation == "empty":
                report["experiments"][1]["cases"] = []
            elif mutation == "baseline":
                report["selected_candidate"]["id"] = "baseline"
            else:
                report["selected_candidate"]["source_sha256"] = "c" * 64
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                self.render(report)

    def test_no_winner_and_no_experiments_remain_explicit(self):
        report = self.report()
        report["selected_candidate"] = None
        html = self.render(report)
        self.assertIn("No repair selected", html)
        report["experiments"] = []
        self.assertIn("No experiments recorded", self.render(report))

    def test_renderer_does_not_mutate_evidence(self):
        report = self.report()
        before = copy.deepcopy(report)
        self.render(report)
        self.assertEqual(before, report)


if __name__ == "__main__":
    unittest.main()
