import unittest
from pathlib import Path

from app.core.paths import (
    APP_CONTROL_DATA_DIR,
    ASSETS_DIR,
    CONFIG_DIR,
    DATA_DIR,
    LOGS_DIR,
    PROJECT_ROOT,
    RUNTIME_DIR,
)


class ProjectPathsTests(unittest.TestCase):
    def test_project_root_is_repository_root(self):
        expected_root = Path(__file__).resolve().parent.parent
        self.assertEqual(PROJECT_ROOT, expected_root)
        self.assertTrue((PROJECT_ROOT / "main.py").is_file())

    def test_static_and_runtime_directories_stay_under_project_root(self):
        self.assertEqual(ASSETS_DIR, PROJECT_ROOT / "assets")
        self.assertEqual(LOGS_DIR, PROJECT_ROOT / "logs")
        self.assertEqual(DATA_DIR, PROJECT_ROOT / "data")
        self.assertEqual(CONFIG_DIR, DATA_DIR / "config")
        self.assertEqual(APP_CONTROL_DATA_DIR, DATA_DIR / "app_control")
        self.assertEqual(RUNTIME_DIR, DATA_DIR / "runtime")

    def test_dotenv_location_can_be_derived_from_project_root(self):
        self.assertEqual(PROJECT_ROOT / ".env", Path(__file__).resolve().parent.parent / ".env")


if __name__ == "__main__":
    unittest.main()
