from dataclasses import replace
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from app.settings.api_groups import APIGroup, APIGroupKey, APIGroupSettings
from app.settings.editing import group_feedback
from app.settings.model import ApiKeyEntry, SettingsValidationError
from app.settings.session import SettingsSession
from tests.settings_helpers import FakeSettingsBackend


class SettingsSessionTests(unittest.TestCase):
    def setUp(self):
        self.backend = FakeSettingsBackend()
        self.session = SettingsSession(self.backend)

    def group_session(self, groups=None):
        backend = Mock(wraps=self.backend)
        backend.save.side_effect = lambda snapshot, **options: self.backend.save(snapshot)
        group_backend = Mock()
        group_backend.load.return_value = groups or APIGroupSettings()
        return SettingsSession(backend, group_backend), backend

    def test_draft_is_independent_of_widgets_and_cancel_never_saves(self):
        self.session.update({"width": 450, "model": "draft-model"})
        self.assertTrue(self.session.is_dirty)
        self.assertEqual(self.backend.saved, [])
        self.session.discard()
        self.assertEqual(self.session.snapshot, self.backend.snapshot)
        self.assertFalse(self.session.is_dirty)

    def test_empty_keys_are_ignored_and_names_are_normalized_in_application_layer(self):
        self.session.update({"api_keys": (ApiKeyEntry("ignored", "  "),)})
        self.assertFalse(self.session.is_dirty)
        self.session.update({"api_keys": (ApiKeyEntry("  ", " test-key "),)})
        self.assertEqual(self.session.snapshot.api_keys, (ApiKeyEntry("Key 1", "test-key"),))

    def test_failed_apply_keeps_original_baseline_and_draft(self):
        original = self.session.original_snapshot
        self.session.update({"width": 450})
        with patch.object(self.backend, "save", side_effect=OSError("failure")):
            with self.assertRaises(OSError):
                self.session.apply()
        self.assertEqual(self.session.original_snapshot, original)
        self.assertEqual(self.session.snapshot.width, 450)
        self.assertTrue(self.session.is_dirty)

    def test_successful_apply_updates_baseline_and_reload_reads_external_changes(self):
        self.session.update({"model": " changed "})
        self.session.apply()
        self.assertEqual(self.session.snapshot.model, "changed")
        self.assertFalse(self.session.is_dirty)
        self.backend.snapshot = replace(self.backend.snapshot, width=600)
        self.session.reload()
        self.assertEqual(self.session.snapshot.width, 600)

    def test_group_mode_ignores_legacy_fields_and_saves_one_bundle(self):
        session, backend = self.group_session()
        original = session.snapshot
        session.update({"model": "hidden", "api_keys": (ApiKeyEntry("", "hidden"),), "width": 400})
        group = APIGroup("g", " New ", " https://example.test/v1 ", " model ", auth_mode="none")
        session.update_groups(APIGroupSettings((group,), "g"))
        session.apply()
        self.assertEqual(session.snapshot.model, original.model)
        self.assertEqual(session.snapshot.api_keys, original.api_keys)
        backend.save.assert_called_once_with(
            replace(original, width=400), api_groups=session.groups, group_settings_mode=True)
        self.assertEqual(session.groups.groups[0].base_url, "https://example.test/v1")

    def test_environment_keys_store_only_references_and_blank_rows_are_omitted(self):
        session, _backend = self.group_session()
        keys = (APIGroupKey("empty", "", "  "),
                APIGroupKey("env", "", "old-secret", source="environment"))
        group = APIGroup("g", "group", "https://example.test", "model", keys=keys)
        with patch.dict("os.environ", {"OPENAI_API_KEY": "environment-secret"}):
            session.update_groups(APIGroupSettings((group,), "g"))
            self.assertTrue(group_feedback(session.groups).environment_available)
        self.assertEqual(session.groups.groups[0].keys,
                         (APIGroupKey("env", "Key 1", source="environment", environment_variable="OPENAI_API_KEY"),))

    def test_completion_endpoint_is_blocked_without_any_ui_validation(self):
        session, backend = self.group_session()
        group = APIGroup("g", "group", "https://example.test/v1/chat/completions", "model", auth_mode="none")
        session.update_groups(APIGroupSettings((group,), "g"))
        with self.assertRaisesRegex(SettingsValidationError, "根路徑"):
            session.apply()
        backend.save.assert_not_called()

    def test_malformed_url_feedback_does_not_crash_and_apply_rejects_it(self):
        session, backend = self.group_session()
        group = APIGroup("g", "group", "http://[broken", "model", auth_mode="none")
        session.update_groups(APIGroupSettings((group,), "g"))
        self.assertTrue(group_feedback(session.groups).status)
        with self.assertRaises(SettingsValidationError):
            session.apply()
        backend.save.assert_not_called()

    def test_migration_preview_and_cancel_do_not_write(self):
        group_backend = Mock()
        group_backend.load.return_value = None
        group_backend.store.get_legacy_api_values.return_value = {
            "BaseUrl": "https://example.test/v1", "Model": "model", "ApiKey": "test-key"}
        with patch.dict("os.environ", {"OPENAI_API_KEY": ""}):
            session = SettingsSession(self.backend, group_backend)
        self.assertEqual(len(session.groups.groups), 1)
        self.assertFalse(session.is_dirty)
        session.discard()
        group_backend.save.assert_not_called()
        self.assertEqual(self.backend.saved, [])

    def test_corrupt_group_data_is_preserved_while_other_settings_can_save(self):
        group_backend = SimpleNamespace(load=Mock(side_effect=SettingsValidationError("broken")))
        backend = Mock(wraps=self.backend)
        backend.save.side_effect = lambda snapshot, **options: self.backend.save(snapshot)
        session = SettingsSession(backend, group_backend)
        self.assertEqual(session.group_error, "broken")
        session.update({"width": 400})
        session.apply()
        self.assertNotIn("api_groups", backend.save.call_args.kwargs)
        self.assertEqual(self.backend.snapshot.width, 400)


if __name__ == "__main__":
    unittest.main()
