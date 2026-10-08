import configparser
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.core.config_manager import (
    ConfigManager,
    config_manager,
    read_layered_ini,
    read_layered_json,
    write_text_bundle_atomically,
)
from app.core.paths import CONFIG_DIR, PROJECT_ROOT, RUNTIME_DIR, ProjectPaths


class ConfigManagerPathTests(unittest.TestCase):
    def test_tools_path_is_explicit_and_independent_of_app_ini_name(self):
        root = PROJECT_ROOT / "__path_mapping_test__"
        paths = ProjectPaths(root, root / "user-data")
        manager = object.__new__(ConfigManager)
        manager._configure_paths(paths)
        manager.config_ini_path = str(root / "another-location" / "app.ini")

        self.assertEqual(Path(manager.tools_json_path), paths.tools_json)
        self.assertEqual(manager._tools_path(), paths.tools_json)

    def test_config_manager_accepts_categorized_paths_without_writing_files(self):
        root = PROJECT_ROOT / "__categorized_path_test__"
        paths = ProjectPaths(root, categorized_data=True)
        manager = object.__new__(ConfigManager)
        manager._configure_paths(paths)

        self.assertEqual(Path(manager.config_ini_path), paths.app_ini)
        self.assertEqual(Path(manager.prompt_json_path), paths.prompt_json)
        self.assertEqual(Path(manager.api_groups_json_path), paths.api_groups_json)
        self.assertEqual(Path(manager.tools_json_path), paths.tools_json)
        self.assertEqual(Path(manager.history_json_path), paths.history_json)
        self.assertEqual(Path(manager.memory_json_path), paths.memory_json)
        self.assertEqual(Path(manager.api_ini_path), paths.legacy_api_ini)
        self.assertFalse(root.exists())

    def test_static_and_runtime_files_are_separated(self):
        self.assertEqual(Path(config_manager.default_config_ini_path), CONFIG_DIR / "app.defaults.ini")
        self.assertEqual(Path(config_manager.default_prompt_json_path), CONFIG_DIR / "prompt.json")
        self.assertEqual(Path(config_manager.prompt_json_path), CONFIG_DIR / "prompt.user.json")
        self.assertEqual(Path(config_manager.config_ini_path), CONFIG_DIR / "app.ini")
        self.assertEqual(Path(config_manager.api_ini_path), RUNTIME_DIR / "api.ini")
        self.assertEqual(Path(config_manager.history_json_path), RUNTIME_DIR / "history.json")
        self.assertEqual(Path(config_manager.memory_json_path), RUNTIME_DIR / "memory.json")
        self.assertEqual(Path(config_manager.env_path), CONFIG_DIR / ".env")

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

    def test_runtime_prompt_values_override_tracked_defaults(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            defaults = root / "prompt.defaults.json"
            runtime = root / "prompt.json"
            defaults.write_text(
                json.dumps({"name": "Nova", "selected_personality": "warm_companion"}),
                encoding="utf-8",
            )
            runtime.write_text(
                json.dumps({"selected_personality": "custom", "custom_personality": "Be concise."}),
                encoding="utf-8",
            )

            prompt = read_layered_json(defaults, runtime)

            self.assertEqual(prompt["name"], "Nova")
            self.assertEqual(prompt["selected_personality"], "custom")
            self.assertEqual(prompt["custom_personality"], "Be concise.")

    def test_invalid_runtime_prompt_does_not_hide_tracked_defaults(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            defaults = root / "prompt.defaults.json"
            runtime = root / "prompt.json"
            defaults.write_text(json.dumps({"name": "Nova"}), encoding="utf-8")
            runtime.write_text("not-json", encoding="utf-8")
            manager = object.__new__(ConfigManager)
            manager.default_prompt_json_path = str(defaults)
            manager.prompt_json_path = str(runtime)

            prompt_data = manager.get_prompt()

            self.assertEqual(prompt_data, {"name": "Nova"})

    def test_atomic_bundle_restores_replaced_files_when_later_replace_fails(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first = root / "first.ini"
            second = root / "second.ini"
            first.write_text("first-old", encoding="utf-8")
            second.write_text("second-old", encoding="utf-8")
            real_replace = os.replace
            replace_count = 0

            def fail_second_replace(source, destination):
                nonlocal replace_count
                replace_count += 1
                if replace_count == 2:
                    raise OSError("replace failed")
                real_replace(source, destination)

            with patch("app.core.config_manager.os.replace", side_effect=fail_second_replace):
                with self.assertRaises(OSError):
                    write_text_bundle_atomically({first: "first-new", second: "second-new"})

            self.assertEqual(first.read_text(encoding="utf-8"), "first-old")
            self.assertEqual(second.read_text(encoding="utf-8"), "second-old")

    def test_settings_bundle_writes_each_runtime_file_with_preserved_options(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manager = object.__new__(ConfigManager)
            manager.config_ini_path = str(root / "app.ini")
            manager.api_ini_path = str(root / "api.ini")
            manager.prompt_json_path = str(root / "prompt.json")
            manager.general_config = configparser.ConfigParser()
            manager.general_config.read_dict({"General": {"PositionX": "15"}})
            manager.api_config = configparser.ConfigParser()
            manager.api_config.read_dict({"API": {"VerifySSL": "false"}})

            manager.save_settings_bundle(
                general_values={"Width": 360},
                api_values={"Model": "test-model"},
                api_key_entries=[{"name": "Primary", "key": "secret-value"}],
                prompt_values={"selected_personality": "custom", "custom_personality": "Be kind."},
            )

            general = configparser.ConfigParser()
            general.read(manager.config_ini_path, encoding="utf-8")
            api = configparser.ConfigParser()
            api.read(manager.api_ini_path, encoding="utf-8")
            prompt_data = json.loads(Path(manager.prompt_json_path).read_text(encoding="utf-8"))
            self.assertEqual(general.getint("General", "Width"), 360)
            self.assertEqual(general.getint("General", "PositionX"), 15)
            self.assertEqual(api.get("API", "Model"), "test-model")
            self.assertFalse(api.getboolean("API", "VerifySSL"))
            self.assertIn("secret-value", api.get("API", "ApiKeys"))
            self.assertEqual(prompt_data["selected_personality"], "custom")

    def test_environment_api_key_is_not_copied_into_editable_entries(self):
        manager = object.__new__(ConfigManager)
        manager.api_config = configparser.ConfigParser()
        manager.api_config.read_dict({"API": {"ApiKey": "saved-key"}})

        with patch.dict(os.environ, {"OPENAI_API_KEY": "environment-key"}):
            entries = manager.get_api_key_entries()

        self.assertEqual(entries, [{"name": "Key 1", "key": "saved-key"}])


if __name__ == "__main__":
    unittest.main()
