import tempfile
import unittest
from pathlib import Path

from app.core.config_manager import config_manager, read_layered_ini
from app.core.paths import CONFIG_DIR, PROJECT_ROOT, RUNTIME_DIR


class ConfigManagerPathTests(unittest.TestCase):
    def test_static_and_runtime_files_are_separated(self):
        self.assertEqual(Path(config_manager.default_config_ini_path), CONFIG_DIR / "app.defaults.ini")
        self.assertEqual(Path(config_manager.prompt_json_path), CONFIG_DIR / "prompt.json")
        self.assertEqual(Path(config_manager.config_ini_path), RUNTIME_DIR / "app.ini")
        self.assertEqual(Path(config_manager.api_ini_path), RUNTIME_DIR / "api.ini")
        self.assertEqual(Path(config_manager.history_json_path), RUNTIME_DIR / "history.json")
        self.assertEqual(Path(config_manager.memory_json_path), RUNTIME_DIR / "memory.json")
        self.assertEqual(Path(config_manager.env_path), PROJECT_ROOT / ".env")

        defaults = read_layered_ini(config_manager.default_config_ini_path, "missing-runtime.ini")
        self.assertFalse(defaults.has_option("General", "PositionX"))
        self.assertFalse(defaults.has_option("General", "PositionY"))

    def test_runtime_values_override_tracked_defaults(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            defaults = root / "defaults.ini"
            runtime = root / "runtime.ini"
            defaults.write_text("[General]\nwidth=300\nheight=400\n", encoding="utf-8")
            runtime.write_text("[General]\nwidth=500\n", encoding="utf-8")

            config = read_layered_ini(defaults, runtime)

            self.assertEqual(config.getint("General", "width"), 500)
            self.assertEqual(config.getint("General", "height"), 400)


if __name__ == "__main__":
    unittest.main()
