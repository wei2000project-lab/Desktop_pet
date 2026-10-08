import unittest
from pathlib import Path

from app.core.paths import (
    APP_CONTROL_DATA_DIR,
    ASSETS_DIR,
    CONFIG_DIR,
    DATA_DIR,
    LOGS_DIR,
    PET_ANIMATIONS_DIR,
    PET_ASSETS_DIR,
    PET_EMOTIONS_DIR,
    PROJECT_ROOT,
    PROJECT_PATHS,
    ProjectPaths,
    RUNTIME_DIR,
)


class ProjectPathsTests(unittest.TestCase):
    def test_project_root_is_repository_root(self):
        expected_root = Path(__file__).resolve().parent.parent
        self.assertEqual(PROJECT_ROOT, expected_root)
        self.assertTrue((PROJECT_ROOT / "main.py").is_file())

    def test_static_and_runtime_directories_stay_under_project_root(self):
        self.assertEqual(ASSETS_DIR, PROJECT_ROOT / "assets")
        self.assertEqual(PET_ASSETS_DIR, ASSETS_DIR / "pet")
        self.assertEqual(PET_ANIMATIONS_DIR, PET_ASSETS_DIR / "animations")
        self.assertEqual(PET_EMOTIONS_DIR, PET_ASSETS_DIR / "emotions")
        self.assertEqual(LOGS_DIR, PROJECT_ROOT / "logs")
        self.assertEqual(DATA_DIR, PROJECT_ROOT / "data")
        self.assertEqual(CONFIG_DIR, DATA_DIR / "config")
        self.assertEqual(APP_CONTROL_DATA_DIR, DATA_DIR / "app_control")
        self.assertEqual(RUNTIME_DIR, DATA_DIR / "runtime")

    def test_dotenv_location_can_be_derived_from_project_root(self):
        self.assertEqual(PROJECT_ROOT / ".env", Path(__file__).resolve().parent.parent / ".env")

    def test_logger_still_writes_under_project_logs_directory(self):
        from app.utils import logger as logger_module

        self.assertEqual(Path(logger_module.default_log_path), LOGS_DIR / "app.log")

    def test_injected_roots_cover_every_current_data_file_without_creating_them(self):
        root = PROJECT_ROOT / "__path_mapping_test__"
        runtime = root / "test-user-data"
        paths = ProjectPaths(root / "checkout", runtime)

        self.assertEqual(paths.default_app_ini, root / "checkout/data/config/app.defaults.ini")
        self.assertEqual(paths.default_prompt_json, root / "checkout/data/config/prompt.json")
        self.assertEqual(paths.app_aliases_json, root / "checkout/data/app_control/aliases.json")
        self.assertEqual(paths.app_ini, runtime / "app.ini")
        self.assertEqual(paths.legacy_api_ini, runtime / "api.ini")
        self.assertEqual(paths.api_groups_json, runtime / "api_groups.json")
        self.assertEqual(paths.prompt_json, runtime / "prompt.json")
        self.assertEqual(paths.tools_json, runtime / "tools.json")
        self.assertEqual(paths.history_json, runtime / "history.json")
        self.assertEqual(paths.memory_json, runtime / "memory.json")
        self.assertEqual(paths.preferences_json, runtime / "preferences.json")
        self.assertEqual(paths.apps_json, runtime / "apps.json")
        self.assertEqual(paths.env_file, root / "checkout/.env")
        self.assertEqual(paths.app_log, root / "checkout/logs/app.log")
        self.assertFalse(runtime.exists())
        self.assertEqual(PROJECT_PATHS.runtime_dir, RUNTIME_DIR)

    def test_categorized_layout_uses_only_existing_data_categories(self):
        root = PROJECT_ROOT / "__categorized_path_test__"
        runtime = root / "test-user-data"
        paths = ProjectPaths(root / "checkout", runtime, categorized_data=True)

        self.assertEqual(paths.default_app_ini, root / "checkout/data/config/app.defaults.ini")
        self.assertEqual(paths.default_prompt_json, root / "checkout/data/config/prompt.json")
        self.assertEqual(paths.app_ini, root / "checkout/data/config/app.ini")
        self.assertEqual(paths.prompt_json, root / "checkout/data/config/prompt.user.json")
        self.assertEqual(paths.api_groups_json, root / "checkout/data/config/api_groups.json")
        self.assertEqual(paths.tools_json, root / "checkout/data/config/tools.json")
        self.assertEqual(paths.app_aliases_json, root / "checkout/data/app_control/aliases.json")
        self.assertEqual(paths.preferences_json, root / "checkout/data/app_control/preferences.json")
        self.assertEqual(paths.apps_json, root / "checkout/data/app_control/apps.json")
        self.assertEqual(paths.history_json, runtime / "history.json")
        self.assertEqual(paths.memory_json, runtime / "memory.json")
        self.assertEqual(paths.legacy_api_ini, runtime / "api.ini")
        self.assertEqual(paths.env_file, root / "checkout/.env")
        self.assertEqual(paths.app_log, root / "checkout/logs/app.log")
        self.assertFalse((root / "checkout").exists())
        self.assertFalse(runtime.exists())


if __name__ == "__main__":
    unittest.main()
