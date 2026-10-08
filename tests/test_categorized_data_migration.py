import json
import tempfile
import unittest
from pathlib import Path

from app.core.categorized_data_migration import (
    CategorizedDataMigrationError, migrate_categorized_data, prepare_categorized_data,
)
from app.core.dotenv_file import DotEnvFile
from app.core.paths import ProjectPaths
from app.settings.api_groups import (
    APIGroup, APIGroupKey, APIGroupSettings, deserialize_api_groups, serialize_api_groups,
)


class CategorizedDataMigrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.old = ProjectPaths(self.root)
        self.new = ProjectPaths(self.root, categorized_data=True)
        self.old.runtime_dir.mkdir(parents=True)
        self.old.app_ini.write_text("[General]\nWidth=321\n", encoding="utf-8")
        self.old.prompt_json.write_text('{"selected_personality":"custom"}\n', encoding="utf-8")
        group = APIGroup("group", "測試", "https://example.test/v1", "model",
                         keys=(APIGroupKey("key", "主用", "fake-group-secret"),))
        self.old.api_groups_json.write_text(
            serialize_api_groups(APIGroupSettings((group,), group.id)), encoding="utf-8",
        )
        self.old.tools_json.write_text(
            json.dumps({"tavily_api_key": "fake-tool-secret", "enabled": True}), encoding="utf-8",
        )
        self.old.preferences_json.write_text('{"preferred_apps":{"browser":"Example"}}', encoding="utf-8")
        self.old.apps_json.write_text('[{"name":"Example"}]', encoding="utf-8")
        self.old.history_json.write_text('[{"role":"user","content":"hello"}]', encoding="utf-8")
        self.old.memory_json.write_text('{"topic":"example"}', encoding="utf-8")
        self.old.legacy_api_ini.write_text(
            '[API]\nBaseUrl=https://example.test/v1\nModel=model\nApiKey=fake-group-secret\n', encoding="utf-8",
        )
        self.old.env_file.write_text("# comment\nUNRELATED=keep\n", encoding="utf-8")
        self.old_bytes = {path: path.read_bytes() for path in self.old.runtime_dir.iterdir()}
        self.old_bytes[self.old.env_file] = self.old.env_file.read_bytes()

    def test_prepare_is_read_only_then_migrate_preserves_all_sources(self):
        contents, originals = prepare_categorized_data(self.new)
        self.assertEqual(len(contents), 7)
        self.assertEqual(originals, self.old_bytes)
        self.assertTrue(all(not path.exists() for path in contents))

        migrated = migrate_categorized_data(self.new)
        self.assertEqual(len(migrated), 7)
        self.assertEqual({path: path.read_bytes() for path in self.old_bytes}, self.old_bytes)
        self.assertEqual(self.new.app_ini.read_text(encoding="utf-8"), self.old.app_ini.read_text(encoding="utf-8"))
        self.assertEqual(json.loads(self.new.prompt_json.read_text(encoding="utf-8")),
                         json.loads(self.old.prompt_json.read_text(encoding="utf-8")))
        self.assertEqual(json.loads(self.new.preferences_json.read_text(encoding="utf-8")),
                         json.loads(self.old.preferences_json.read_text(encoding="utf-8")))
        self.assertEqual(json.loads(self.new.apps_json.read_text(encoding="utf-8")),
                         json.loads(self.old.apps_json.read_text(encoding="utf-8")))
        groups = deserialize_api_groups(self.new.api_groups_json.read_text(encoding="utf-8"))
        self.assertEqual(groups.schema_version, 2)
        self.assertEqual(groups.groups[0].keys[0].key, "")
        self.assertNotIn("fake-group-secret", self.new.api_groups_json.read_text(encoding="utf-8"))
        self.assertNotIn("fake-tool-secret", self.new.tools_json.read_text(encoding="utf-8"))
        values = DotEnvFile(self.new.env_file).read_values()
        self.assertEqual(values[groups.groups[0].keys[0].environment_variable], "fake-group-secret")
        self.assertEqual(values["NOVA_TOOL_API_KEY"], "fake-tool-secret")
        self.assertEqual(values["UNRELATED"], "keep")

    def test_existing_destination_stops_without_overwrite(self):
        self.new.config_dir.mkdir(parents=True)
        self.new.app_ini.write_text("keep", encoding="utf-8")
        with self.assertRaises(CategorizedDataMigrationError):
            migrate_categorized_data(self.new)
        self.assertEqual(self.new.app_ini.read_text(encoding="utf-8"), "keep")
        self.assertFalse(self.new.api_groups_json.exists())
        self.assertEqual({path: path.read_bytes() for path in self.old_bytes}, self.old_bytes)

    def test_unmatched_legacy_key_stops_before_any_destination_is_created(self):
        self.old.legacy_api_ini.write_text(
            '[API]\nBaseUrl=https://example.test/v1\nModel=model\nApiKey=fake-other-secret\n', encoding="utf-8",
        )
        with self.assertRaises(CategorizedDataMigrationError):
            migrate_categorized_data(self.new)
        self.assertFalse(self.new.app_ini.exists())
        self.assertFalse(self.new.env_file.exists())


if __name__ == "__main__":
    unittest.main()
