import configparser
import json
import os
import tempfile
import unittest
from dataclasses import FrozenInstanceError, replace
from pathlib import Path
from unittest.mock import patch

from app.core.config_manager import ConfigManager
from app.core.paths import API_GROUPS_JSON_PATH, RUNTIME_DIR
from app.settings import SettingsService, SettingsSnapshot
from app.settings.api_group_service import APIGroupService
from app.settings.api_groups import (
    APIGroup, APIGroupDataError, APIGroupKey, APIGroupSettings,
    deserialize_api_groups, migrate_legacy_api, serialize_api_groups, validate_api_groups,
)


def sample_settings():
    group = APIGroup("group-1", "測試", "https://example.test/v1", "test-model",
                     keys=(APIGroupKey("key-1", "主用", "fake-test-key"),))
    return APIGroupSettings((group,), group.id)


class GroupModelTests(unittest.TestCase):
    def test_round_trip_and_immutability(self):
        settings = sample_settings()
        self.assertEqual(deserialize_api_groups(serialize_api_groups(settings)), settings)
        with self.assertRaises(FrozenInstanceError):
            settings.groups[0].name = "changed"
        self.assertNotIn("fake-test-key", repr(settings))

    def test_empty_container_is_valid(self):
        self.assertEqual(deserialize_api_groups(serialize_api_groups(APIGroupSettings())), APIGroupSettings())

    def test_duplicate_group_and_key_ids_rejected(self):
        settings = sample_settings()
        group = settings.groups[0]
        for invalid in (replace(settings, groups=(group, group)),
                        replace(settings, groups=(group, replace(group, id="group-2"))),
                        replace(settings, groups=(replace(group, keys=group.keys * 2),))):
            with self.assertRaises(APIGroupDataError):
                validate_api_groups(invalid)

    def test_dangling_active_group_rejected(self):
        with self.assertRaises(APIGroupDataError):
            validate_api_groups(replace(sample_settings(), active_group_id="missing"))

    def test_invalid_group_fields_rejected(self):
        settings = sample_settings()
        changes = (
            {"id": ""}, {"name": " "}, {"model": ""}, {"base_url": "bad"},
            {"base_url": "https://user:secret@example.test"},
            {"base_url": "https://example.test?key=fake-test-key"},
            {"base_url": "https://example.test#secret"},
            {"base_url": "https://example.test:99999"},
            {"base_url": "https://example.test/has space"},
            {"temperature": float("nan")}, {"temperature": float("inf")},
            {"temperature": True}, {"temperature": 2.1}, {"temperature": "0.7"},
            {"verify_ssl": "true"}, {"auth_mode": "unknown"}, {"keys": []},
        )
        for change in changes:
            with self.subTest(change=change):
                with self.assertRaises(APIGroupDataError) as raised:
                    validate_api_groups(replace(settings, groups=(replace(settings.groups[0], **change),)))
                self.assertNotIn("fake-test-key", str(raised.exception))

    def test_invalid_key_fields_rejected(self):
        settings = sample_settings()
        group = settings.groups[0]
        for change in ({"priority": 0}, {"priority": 11}, {"priority": "X"},
                       {"priority": True}, {"enabled": 1}, {"key": " "},
                       {"id": ""}, {"name": ""}, {"source": "unknown"},
                       {"environment_variable": "OPENAI_API_KEY"},
                       {"source": "environment", "environment_variable": "OPENAI_API_KEY"},
                       {"source": "environment", "key": "", "environment_variable": "OTHER"}):
            with self.subTest(change=change):
                with self.assertRaises(APIGroupDataError):
                    validate_api_groups(replace(settings, groups=(replace(group, keys=(replace(group.keys[0], **change),)),)))

    def test_environment_none_and_same_priority_supported(self):
        settings = sample_settings()
        group = settings.groups[0]
        env = APIGroupKey("key-2", "環境", priority=1, enabled=False,
                          source="environment", environment_variable="OPENAI_API_KEY")
        settings = replace(settings, groups=(replace(group, keys=(*group.keys, env)),
                                            APIGroup("local", "本地", "http://127.0.0.1:8080/v1", "local-model", auth_mode="none")))
        self.assertEqual(deserialize_api_groups(serialize_api_groups(settings)), settings)

    def test_corrupt_unknown_version_and_unknown_fields_rejected(self):
        payload = json.loads(serialize_api_groups(sample_settings()))
        for value in ("fake-test-key broken json", "[]", "null", "{}",
                      '{"schema_version":1,"schema_version":1}',
                      json.dumps({**payload, "schema_version": 2}),
                      json.dumps({**payload, "schema_version": True}),
                      json.dumps({**payload, "unknown": "fake-test-key"}),
                      json.dumps({**payload, "groups": [None]})):
            with self.subTest(value=value):
                with self.assertRaises(APIGroupDataError) as raised:
                    deserialize_api_groups(value)
                self.assertNotIn("fake-test-key", str(raised.exception))


class LegacyMigrationTests(unittest.TestCase):
    def test_all_fields_and_multiple_named_keys_preserved(self):
        entries = [{"name": f"測試 {i}", "key": f"fake-key-{i}"} for i in range(12)]
        settings = migrate_legacy_api({"BaseUrl": "https://example.test/v1", "Model": "other-model",
                                       "Temperature": "1.2", "VerifySSL": "false",
                                       "ApiKeys": json.dumps(entries), "ApiKey": "fake-key-0"})
        group = settings.groups[0]
        self.assertEqual(settings.active_group_id, group.id)
        self.assertEqual((group.base_url, group.model, group.temperature, group.verify_ssl),
                         ("https://example.test/v1", "other-model", 1.2, False))
        self.assertEqual([(key.name, key.key) for key in group.keys], [(e["name"], e["key"]) for e in entries])
        self.assertEqual([key.priority for key in group.keys], [*range(1, 11), 10, 10])
        self.assertTrue(all(key.enabled for key in group.keys))

    def test_single_legacy_key_and_environment_reference(self):
        settings = migrate_legacy_api({"ApiKey": "fake-stored-key"}, True)
        group = settings.groups[0]
        self.assertEqual(len(group.keys), 2)
        self.assertEqual(group.keys[0].source, "environment")
        self.assertEqual(group.keys[0].key, "")
        self.assertEqual(group.keys[0].environment_variable, "OPENAI_API_KEY")
        self.assertEqual(group.keys[1].key, "fake-stored-key")
        self.assertEqual([key.priority for key in group.keys], [1, 1])

    def test_unconfigured_is_not_assumed_to_be_local(self):
        self.assertEqual(migrate_legacy_api({}), APIGroupSettings())
        settings = migrate_legacy_api({"BaseUrl": "http://localhost:8080/v1", "Model": "local"})
        self.assertEqual(settings.groups[0].auth_mode, "api_key")
        self.assertEqual(settings.groups[0].keys, ())

    def test_malformed_old_data_does_not_silently_drop_keys(self):
        for legacy in ({"ApiKeys": "fake-key not json", "ApiKey": "fallback"},
                       {"ApiKeys": "{}"}, {"ApiKeys": '[{"key":12}]'},
                       {"ApiKeys": '[{"key":"fake-key","extra":1}]'},
                       {"ApiKey": "fake-key", "Temperature": "nan"},
                       {"ApiKey": "fake-key", "VerifySSL": "invalid"},
                       {"ApiKey": "fake-key", "BaseUrl": ""}):
            with self.subTest(legacy=legacy):
                with self.assertRaises(APIGroupDataError) as raised:
                    migrate_legacy_api(legacy)
                self.assertNotIn("fake-key", str(raised.exception))

    def test_blank_names_and_no_environment_reference(self):
        settings = migrate_legacy_api({"ApiKeys": '[{"name":" ","key":" fake-key "}]'})
        self.assertEqual(settings.groups[0].keys[0].name, "Key 1")
        self.assertEqual(settings.groups[0].keys[0].key, "fake-key")
        self.assertEqual(settings.groups[0].keys[0].source, "stored")


class GroupPersistenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.store = object.__new__(ConfigManager)
        self.store.api_groups_json_path = str(self.root / "api_groups.json")
        self.store.config_ini_path = str(self.root / "app.ini")
        self.store.api_ini_path = str(self.root / "api.ini")
        self.store.prompt_json_path = str(self.root / "prompt.json")
        self.store.default_prompt_json_path = str(self.root / "missing-defaults.json")
        self.store.general_config = configparser.ConfigParser()
        self.store.general_config.read_dict({"General": {"Width": "250"}})
        self.store.api_config = configparser.ConfigParser()
        self.store.api_config.read_dict({"API": {"ApiKey": "fake-stored-key"}})
        self.events = []
        self.service = APIGroupService(self.store, self.events.append)
        self.path = Path(self.store.api_groups_json_path)

    def test_runtime_path_and_read_does_not_create_file(self):
        self.assertEqual(API_GROUPS_JSON_PATH, RUNTIME_DIR / "api_groups.json")
        self.assertIsNone(self.service.load())
        self.assertFalse(self.path.exists())
        self.assertEqual(self.events, [])

    def test_config_initialization_does_not_read_or_write_groups(self):
        manager = object.__new__(ConfigManager)
        with (patch("app.core.config_manager.migrate_legacy_runtime_data") as migration,
              patch.object(manager, "load_env"), patch.object(manager, "load_configs"),
              patch.object(manager, "get_api_group_contents") as read,
              patch.object(manager, "save_api_group_contents") as write):
            migration.return_value.failed = ()
            manager._init()
        read.assert_not_called()
        write.assert_not_called()
        self.assertEqual(Path(manager.api_groups_json_path), API_GROUPS_JSON_PATH)

    def test_opt_in_migration_is_idempotent_and_preserves_old_file(self):
        legacy = Path(self.store.api_ini_path)
        legacy.write_text("original legacy data", encoding="utf-8")
        first = self.service.migrate({"OPENAI_API_KEY": "fake-env-secret"})
        before = self.path.read_bytes()
        second = self.service.migrate({})
        self.assertEqual(first, second)
        self.assertEqual(self.path.read_bytes(), before)
        self.assertNotIn("fake-env-secret", self.path.read_text(encoding="utf-8"))
        self.assertEqual(legacy.read_text(encoding="utf-8"), "original legacy data")
        self.assertEqual(self.events, ["config_updated"])

    def test_valid_empty_file_does_not_resurrect_legacy(self):
        self.service.save(APIGroupSettings())
        self.assertEqual(self.service.migrate({"OPENAI_API_KEY": "fake-env-secret"}), APIGroupSettings())
        self.assertEqual(self.events, ["config_updated"])

    def test_corrupt_file_is_not_overwritten_or_migrated(self):
        self.path.write_text("fake-secret broken json", encoding="utf-8")
        for operation in (self.service.load, lambda: self.service.migrate({}),
                          lambda: self.service.save(sample_settings())):
            with self.assertRaises(APIGroupDataError):
                operation()
            self.assertEqual(self.path.read_text(encoding="utf-8"), "fake-secret broken json")
        self.assertEqual(self.events, [])

    def test_invalid_encoding_and_unknown_version_preserved(self):
        for contents in (b"\xff", serialize_api_groups(replace(sample_settings())).replace('"schema_version": 1', '"schema_version": 9').encode()):
            self.path.write_bytes(contents)
            with self.assertRaises(APIGroupDataError):
                self.service.migrate({})
            self.assertEqual(self.path.read_bytes(), contents)

    def test_migration_failure_does_not_publish_or_leave_partial_file(self):
        with patch("app.core.config_manager.os.replace", side_effect=OSError("fake-secret")):
            with self.assertRaises(APIGroupDataError) as raised:
                self.service.migrate({})
        self.assertNotIn("fake-secret", str(raised.exception))
        self.assertFalse(self.path.exists())
        self.assertEqual(list(self.root.glob("*.tmp")), [])
        self.assertEqual(self.events, [])

    def test_combined_save_writes_groups_and_publishes_once(self):
        settings_service = SettingsService(self.store, self.events.append)
        settings_service.save(SettingsSnapshot(width=400), api_groups=sample_settings())
        self.assertEqual(self.service.load(), sample_settings())
        self.assertEqual(self.store.get_general_int("Width"), 400)
        self.assertEqual(self.events, ["config_updated"])

    def test_old_save_does_not_create_or_touch_group_file(self):
        settings_service = SettingsService(self.store, self.events.append)
        settings_service.save(SettingsSnapshot())
        self.assertFalse(self.path.exists())
        self.service.save(sample_settings())
        before = self.path.read_bytes()
        settings_service.save(SettingsSnapshot(width=300))
        self.assertEqual(self.path.read_bytes(), before)

    def test_saved_runtime_fields_and_environment_reference_are_preserved(self):
        group = APIGroup(
            "custom-group",
            "自訂服務",
            "https://custom.example.test/v1",
            "custom/model-v2",
            temperature=1.4,
            verify_ssl=False,
            keys=(
                APIGroupKey("disabled", "已停用", "fake-disabled-key", 1, False),
                APIGroupKey(
                    "environment",
                    "環境來源",
                    priority=2,
                    source="environment",
                    environment_variable="OPENAI_API_KEY",
                ),
                APIGroupKey("backup", "備用", "fake-backup-key", 3, True),
            ),
        )
        settings = APIGroupSettings((group,), group.id)

        self.service.save(settings)
        loaded = self.service.load()
        snapshot = self.service.resolve_request(
            environment={"OPENAI_API_KEY": "fake-runtime-env-key"}
        )

        self.assertEqual(loaded, settings)
        self.assertEqual(snapshot.model, "custom/model-v2")
        self.assertEqual(snapshot.temperature, 1.4)
        self.assertFalse(snapshot.verify_ssl)
        self.assertEqual(
            [(candidate.id, candidate.source, candidate.priority) for candidate in snapshot.candidates],
            [("environment", "environment", 2), ("backup", "stored", 3)],
        )
        self.assertNotIn("fake-runtime-env-key", self.path.read_text(encoding="utf-8"))

    def test_combined_save_rolls_back_all_files_and_memory(self):
        settings_service = SettingsService(self.store, self.events.append)
        settings_service.save(SettingsSnapshot(), api_groups=sample_settings())
        paths = [Path(self.store.config_ini_path), Path(self.store.api_ini_path),
                 Path(self.store.prompt_json_path), self.path]
        originals = {path: path.read_bytes() for path in paths}
        real_replace = os.replace
        def fail_group_replace(source, destination):
            if Path(destination) == self.path:
                raise OSError("replace failed")
            real_replace(source, destination)
        with patch("app.core.config_manager.os.replace", side_effect=fail_group_replace):
            with self.assertRaises(OSError):
                settings_service.save(SettingsSnapshot(width=450), api_groups=APIGroupSettings())
        self.assertEqual({path: path.read_bytes() for path in paths}, originals)
        self.assertEqual(self.store.get_general_int("Width"), 250)
        self.assertEqual(self.events, ["config_updated"])

    def test_new_group_file_remains_absent_after_batch_failure(self):
        settings_service = SettingsService(self.store, self.events.append)
        real_replace = os.replace
        def fail_group_replace(source, destination):
            if Path(destination) == self.path:
                raise OSError("replace failed")
            real_replace(source, destination)
        with patch("app.core.config_manager.os.replace", side_effect=fail_group_replace):
            with self.assertRaises(OSError):
                settings_service.save(SettingsSnapshot(), api_groups=sample_settings())
        self.assertEqual(list(self.root.iterdir()), [])
        self.assertEqual(self.events, [])

    def test_corrupt_target_blocks_combined_save_before_other_writes(self):
        self.path.write_text("broken json", encoding="utf-8")
        with self.assertRaises(APIGroupDataError):
            SettingsService(self.store, self.events.append).save(SettingsSnapshot(), api_groups=sample_settings())
        self.assertEqual(len(list(self.root.iterdir())), 1)
        self.assertEqual(self.events, [])


if __name__ == "__main__":
    unittest.main()
