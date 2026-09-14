import json
import tempfile
import unittest
from pathlib import Path

from app.core.data_migration import migrate_legacy_runtime_data


class DataMigrationTests(unittest.TestCase):
    def test_migrates_valid_files_without_deleting_sources(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            legacy, runtime = root / "config", root / "runtime"
            legacy.mkdir()
            (legacy / "api.ini").write_text("[API]\nmodel=test\n", encoding="utf-8")
            (legacy / "config.ini").write_text("[General]\nwidth=300\n", encoding="utf-8")
            for name in ("apps.json", "app_preferences.json", "history.json", "memory.json"):
                (legacy / name).write_text("{}", encoding="utf-8")

            result = migrate_legacy_runtime_data(legacy, runtime)

            self.assertEqual(result.failed, ())
            self.assertEqual(len(result.migrated), 6)
            self.assertTrue((legacy / "api.ini").exists())
            self.assertEqual((runtime / "app.ini").read_text(encoding="utf-8"),
                             "[General]\nwidth=300\n")

    def test_existing_destination_is_never_overwritten(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            legacy, runtime = root / "config", root / "runtime"
            legacy.mkdir()
            runtime.mkdir()
            (legacy / "history.json").write_text('[{"old": true}]', encoding="utf-8")
            (runtime / "history.json").write_text('[{"new": true}]', encoding="utf-8")

            result = migrate_legacy_runtime_data(legacy, runtime)

            self.assertIn("history.json", result.skipped)
            self.assertEqual(json.loads((runtime / "history.json").read_text(encoding="utf-8")),
                             [{"new": True}])

    def test_invalid_source_is_retained_and_does_not_create_destination(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            legacy, runtime = root / "config", root / "runtime"
            legacy.mkdir()
            (legacy / "memory.json").write_text("not-json", encoding="utf-8")

            result = migrate_legacy_runtime_data(legacy, runtime)

            self.assertIn("memory.json", result.failed)
            self.assertTrue((legacy / "memory.json").exists())
            self.assertFalse((runtime / "memory.json").exists())
            self.assertEqual(list(runtime.glob("*.migration.tmp")), [])


if __name__ == "__main__":
    unittest.main()
