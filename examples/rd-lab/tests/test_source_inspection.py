import importlib.util
from pathlib import Path
import tempfile
import unittest


class SourceInspectionTests(unittest.TestCase):
    def test_index_finds_definition_from_allowlisted_source_only(self):
        self.assertIsNotNone(importlib.util.find_spec("rd_lab.source_inspection"))
        from rd_lab.source_inspection import inspect_sources
        if importlib.util.find_spec("index_graph") is None:
            self.skipTest("Optional Index package not installed")
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "program.py").write_text("def normalize(x):\n    return str(x)\n", encoding="utf-8")
            (root / "not_allowed.py").write_text("def private_function(): pass\n", encoding="utf-8")
            result = inspect_sources(root, ["program.py"], "normalize")
            self.assertEqual(result["definitions"][0]["name"], "normalize")
            self.assertEqual(result["definitions"][0]["line"], 1)
            self.assertEqual(result["definitions"][0]["file"], "program.py")
            self.assertEqual(result["source_files"], ["program.py"])
            hidden = inspect_sources(root, ["program.py"], "private_function")
            self.assertEqual(hidden["definitions"], [])
            self.assertNotIn(temporary, str(result))

    def test_inspection_rejects_empty_or_escaping_allowlist(self):
        self.assertIsNotNone(importlib.util.find_spec("rd_lab.source_inspection"))
        from rd_lab.source_inspection import inspect_sources
        with tempfile.TemporaryDirectory() as temporary:
            for files in ([], ["../escape.py"], ["/absolute.py"], ["nested/../escape.py"]):
                with self.subTest(files=files), self.assertRaises(ValueError):
                    inspect_sources(Path(temporary), files, "normalize")


if __name__ == "__main__":
    unittest.main()
