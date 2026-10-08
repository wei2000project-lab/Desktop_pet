import configparser
import json
import os
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from app.core.config_manager import ConfigManager
from app.core.dotenv_file import DotEnvFile
from app.core.paths import ProjectPaths
from app.settings import SettingsService, SettingsSnapshot
from app.settings.api_group_resolver import resolve_api_request
from app.settings.api_group_service import APIGroupService
from app.settings.api_groups import (
    APIGroup, APIGroupDataError, APIGroupKey, APIGroupSettings,
    ENV_SCHEMA_VERSION, deserialize_api_groups, serialize_api_groups,
)
from app.settings.api_groups import managed_key_name
from app.settings.session import SettingsSession
from app.settings.tool_settings import TOOL_KEY_ENV


class EnvDataFormatTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.paths = ProjectPaths(self.root, categorized_data=True)
        self.store = object.__new__(ConfigManager)
        self.store._configure_paths(self.paths)
        self.store.general_config = configparser.ConfigParser()
        self.store.general_config.read_dict({"General": {"Width": "250"}})
        self.store.api_config = configparser.ConfigParser()
        self.store.api_config.add_section("API")
        self.env = DotEnvFile(self.paths.env_file)
        self.events = []
        self.service = SettingsService(self.store, self.events.append)
        self.group_service = APIGroupService(self.store, self.events.append)
        self.environment_patch = patch.dict(os.environ, {}, clear=False)
        self.environment_patch.start()
        self.addCleanup(self.environment_patch.stop)

    @staticmethod
    def draft(*keys):
        group = APIGroup("group", "群組", "https://example.test/v1", "test-model", keys=keys)
        return APIGroupSettings((group,), "group", ENV_SCHEMA_VERSION)

    def save(self, groups):
        return self.service.save(SettingsSnapshot(), api_groups=groups, group_settings_mode=True)

    def test_multiple_keys_round_trip_without_plaintext_in_json_or_ini(self):
        self.paths.env_file.write_text("# user comment\nUNRELATED=keep\n", encoding="utf-8")
        draft = self.draft(
            APIGroupKey("first", "主用", "fake-first-key"),
            APIGroupKey("second", "備用", "fake-second-key", priority=2),
        )
        self.save(draft)

        group_text = self.paths.api_groups_json.read_text(encoding="utf-8")
        ini_text = self.paths.app_ini.read_text(encoding="utf-8")
        self.assertNotIn("fake-first-key", group_text + ini_text)
        self.assertNotIn("fake-second-key", group_text + ini_text)
        self.assertNotIn('"key"', group_text)
        self.assertEqual(json.loads(group_text)["schema_version"], 2)
        self.assertTrue(self.paths.env_file.read_text(encoding="utf-8").startswith("# user comment\nUNRELATED=keep\n"))
        saved = self.group_service.load()
        self.assertEqual([entry.key for entry in saved.groups[0].keys], ["", ""])
        self.assertEqual(len({entry.environment_variable for entry in saved.groups[0].keys}), 2)
        snapshot = resolve_api_request(saved, environment=self.env.read_values())
        self.assertEqual([entry.key for entry in snapshot.candidates], ["fake-first-key", "fake-second-key"])
        self.assertEqual(self.events, ["config_updated"])

    def test_blank_preserves_replace_updates_and_explicit_remove_clears_only_owned_key(self):
        self.paths.env_file.write_text("UNRELATED=keep\n# keep this\n", encoding="utf-8")
        self.save(self.draft(APIGroupKey("first", "主用", "fake-original")))
        saved = self.group_service.load()
        name = saved.groups[0].keys[0].environment_variable
        before = self.paths.env_file.read_bytes()

        self.save(replace(saved, groups=(replace(saved.groups[0], name="改名"),)))
        self.assertEqual(self.paths.env_file.read_bytes(), before)

        whitespace = replace(saved.groups[0].keys[0], key="   ")
        self.save(replace(saved, groups=(replace(saved.groups[0], keys=(whitespace,)),)))
        self.assertEqual(self.paths.env_file.read_bytes(), before)

        changed = replace(saved.groups[0].keys[0], key="fake-replacement")
        self.save(replace(saved, groups=(replace(saved.groups[0], keys=(changed,)),)))
        self.assertEqual(self.env.read_values()[name], "fake-replacement")
        self.assertNotIn("fake-replacement", self.paths.api_groups_json.read_text(encoding="utf-8"))

        current = self.group_service.load()
        self.save(replace(current, groups=(replace(current.groups[0], keys=()),)))
        self.assertNotIn(name, self.env.read_values())
        self.assertEqual(self.env.read_values()["UNRELATED"], "keep")
        self.assertIn("# keep this", self.paths.env_file.read_text(encoding="utf-8"))

    def test_existing_unowned_variable_blocks_new_key_without_changing_files(self):
        name = managed_key_name("first")
        original = f"{name}=unrelated-value\nUNRELATED=keep\n"
        self.paths.env_file.write_text(original, encoding="utf-8")
        with self.assertRaises(ValueError):
            self.save(self.draft(APIGroupKey("first", "主用", "fake-new")))
        self.assertEqual(self.paths.env_file.read_text(encoding="utf-8"), original)
        self.assertFalse(self.paths.api_groups_json.exists())
        self.assertFalse(self.paths.app_ini.exists())

    def test_env_write_failure_restores_settings_and_process_value(self):
        self.save(self.draft(APIGroupKey("first", "主用", "fake-original")))
        saved = self.group_service.load()
        name = saved.groups[0].keys[0].environment_variable
        before = {
            path: path.read_bytes() for path in (
                self.paths.app_ini, self.paths.prompt_json,
                self.paths.api_groups_json, self.paths.env_file,
            )
        }
        changed = replace(saved.groups[0].keys[0], key="fake-replacement")
        draft = replace(saved, groups=(replace(saved.groups[0], keys=(changed,)),))
        real_replace = os.replace

        def fail_env_replace(source, destination):
            if Path(destination) == self.paths.env_file:
                raise OSError("synthetic write failure")
            return real_replace(source, destination)

        with patch("app.core.config_manager.os.replace", side_effect=fail_env_replace):
            with self.assertRaises(OSError):
                self.save(draft)
        self.assertEqual({path: path.read_bytes() for path in before}, before)
        self.assertEqual(os.environ[name], "fake-original")
        self.assertEqual(self.events, ["config_updated"])

    def test_version_two_rejects_plaintext_field_in_saved_json(self):
        settings = self.draft(APIGroupKey("first", "主用", "", environment_variable=managed_key_name("first")))
        payload = json.loads(serialize_api_groups(settings))
        payload["groups"][0]["keys"][0]["key"] = "fake-secret"
        with self.assertRaises(APIGroupDataError):
            deserialize_api_groups(json.dumps(payload))
        with self.assertRaises(APIGroupDataError):
            serialize_api_groups(self.draft(APIGroupKey("first", "主用", "fake-secret")))

    def test_apply_reloads_secret_free_group_and_blank_keeps_existing_key(self):
        session = SettingsSession(self.service, self.group_service)
        session.update_groups(self.draft(APIGroupKey("first", "主用", "fake-first-key")))
        session.apply()
        self.assertFalse(session.is_dirty)
        self.assertEqual(session.groups.groups[0].keys[0].key, "")
        name = session.groups.groups[0].keys[0].environment_variable
        before = self.paths.env_file.read_bytes()

        session.update_groups(replace(
            session.groups,
            groups=(replace(session.groups.groups[0], name="改名"),),
        ))
        session.apply()
        self.assertFalse(session.is_dirty)
        self.assertEqual(self.paths.env_file.read_bytes(), before)
        self.assertEqual(self.env.read_values()[name], "fake-first-key")

    def test_editor_keeps_saved_reference_with_empty_input_and_explicit_delete(self):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtWidgets import QApplication
        from ui.settings.widgets.api_group_editor import APIGroupEditor

        app = QApplication.instance() or QApplication([])
        editor = APIGroupEditor()
        try:
            saved = self.draft(APIGroupKey(
                "first", "主用", "", environment_variable=managed_key_name("first"),
            ))
            editor.load_settings(saved)
            row = editor.group_rows[0]["keys"][0]
            self.assertEqual(row["key"].text(), "")
            self.assertIn("留空", row["key"].placeholderText())
            self.assertEqual(editor.collect_settings(), saved)

            row["key"].setText("fake-replacement")
            self.assertEqual(editor.collect_settings().groups[0].keys[0].key, "fake-replacement")
            editor.remove_key("group", "first")
            self.assertEqual(editor.collect_settings().groups[0].keys, ())
        finally:
            editor.close()
            editor.deleteLater()
            app.processEvents()

    def test_tool_format_preserves_other_settings_and_supports_replace_and_clear(self):
        self.paths.env_file.write_text("# comment\nUNRELATED=keep\n", encoding="utf-8")
        old = {"tavily_api_key": "fake-tool-secret", "enabled": True}
        self.store.save_tool_settings_v2(old)
        saved = self.store.get_tool_settings()
        self.assertEqual(saved["schema_version"], 2)
        self.assertEqual(saved["enabled"], True)
        self.assertNotIn("tavily_api_key", saved)
        self.assertEqual(saved["tavily_api_key_env"], TOOL_KEY_ENV)
        self.assertEqual(self.env.read_values()[TOOL_KEY_ENV], "fake-tool-secret")

        before = self.paths.env_file.read_bytes()
        self.store.save_tool_settings_v2(saved, replacement="")
        self.assertEqual(self.paths.env_file.read_bytes(), before)
        self.store.save_tool_settings_v2(saved, replacement="fake-new-secret")
        self.assertEqual(self.env.read_values()[TOOL_KEY_ENV], "fake-new-secret")
        self.assertNotIn("fake-new-secret", self.paths.tools_json.read_text(encoding="utf-8"))
        self.store.save_tool_settings_v2(saved, clear=True)
        self.assertNotIn(TOOL_KEY_ENV, self.env.read_values())
        self.assertEqual(self.env.read_values()["UNRELATED"], "keep")
        self.assertNotIn("tavily_api_key_env", self.store.get_tool_settings())


if __name__ == "__main__":
    unittest.main()
