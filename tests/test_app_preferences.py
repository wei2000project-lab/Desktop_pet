import tempfile
import unittest
from pathlib import Path

from app.control.preferences import AppPreferenceStore


class AppPreferenceStoreTests(unittest.TestCase):
    def test_saves_and_loads_preferred_app_for_category(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "app_preferences.json"
            store = AppPreferenceStore(path)

            store.set_preference("browser", "Microsoft Edge")

            loaded = AppPreferenceStore(path)
            self.assertEqual(loaded.get_preference("browser"), "Microsoft Edge")

    def test_missing_or_invalid_file_returns_no_preference(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "app_preferences.json"
            path.write_text("{bad json", encoding="utf-8")

            store = AppPreferenceStore(path)

            self.assertEqual(store.get_preference("browser"), "")


if __name__ == "__main__":
    unittest.main()
