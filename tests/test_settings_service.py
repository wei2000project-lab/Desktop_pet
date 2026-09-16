import unittest

from app.settings.model import ApiKeyEntry, SettingsSnapshot, SettingsValidationError
from app.settings.service import SettingsService


class FakeSettingsStore:
    def __init__(self):
        self.saved = None
        self.fail_on_save = False
        self.history_cleared = False
        self.prompt = {
            "personality_options": ["gentle"],
            "custom_personality": "  custom prompt  ",
        }
        self.api = {
            "BaseUrl": "https://api.example.test/v1",
            "Model": "test-model",
            "Temperature": "0.8",
            "VerifySSL": "false",
        }
        self.general = {
            "Width": 320,
            "Height": 330,
            "AlwaysOnTop": False,
            "MaxMemoryTurns": 7,
            "HistoryLimit": 24,
            "ConversationSummaryEnabled": False,
            "ReadingIdleSeconds": 90,
        }

    def get_prompt(self):
        return dict(self.prompt)

    def get_api(self, key, default=None):
        return self.api.get(key, default)

    def get_api_key_entries(self):
        return [{"name": "Primary", "key": "secret-value"}]

    def get_general_int(self, key, default=0):
        return int(self.general.get(key, default))

    def get_general_bool(self, key, default=False):
        return bool(self.general.get(key, default))

    def save_settings_bundle(self, **values):
        if self.fail_on_save:
            raise OSError("save failed")
        self.saved = values

    def clear_history(self):
        self.history_cleared = True


class SettingsServiceTests(unittest.TestCase):
    def setUp(self):
        self.store = FakeSettingsStore()
        self.events = []
        self.service = SettingsService(self.store, self.events.append)

    def test_load_builds_snapshot_and_migrates_legacy_personality(self):
        snapshot = self.service.load()

        self.assertEqual(snapshot.api_keys, (ApiKeyEntry("Primary", "secret-value"),))
        self.assertEqual(snapshot.selected_personality, "warm_companion")
        self.assertEqual(snapshot.custom_personality, "custom prompt")
        self.assertEqual(snapshot.width, 320)
        self.assertFalse(snapshot.verify_ssl)

    def test_save_normalizes_once_and_publishes_once(self):
        snapshot = SettingsSnapshot(
            api_keys=(ApiKeyEntry("", "  secret-value  "),),
            base_url="  https://api.example.test/v1  ",
            model="  test-model  ",
            temperature=0.8,
            selected_personality=" custom ",
            custom_personality="  Be kind.  ",
        )

        normalized = self.service.save(snapshot)

        self.assertEqual(normalized.api_keys, (ApiKeyEntry("Key 1", "secret-value"),))
        self.assertEqual(normalized.base_url, "https://api.example.test/v1")
        self.assertEqual(normalized.selected_personality, "custom")
        self.assertEqual(self.store.saved["api_values"]["Temperature"], "0.8")
        self.assertEqual(self.store.saved["prompt_values"]["custom_personality"], "Be kind.")
        self.assertEqual(self.events, ["config_updated"])

    def test_load_replaces_non_finite_temperature_with_default(self):
        self.store.api["Temperature"] = "nan"

        snapshot = self.service.load()

        self.assertEqual(snapshot.temperature, 0.7)

    def test_invalid_values_are_rejected_before_save(self):
        snapshot = SettingsSnapshot(base_url="not-a-url")

        with self.assertRaises(SettingsValidationError):
            self.service.save(snapshot)

        self.assertIsNone(self.store.saved)
        self.assertEqual(self.events, [])

    def test_failed_save_does_not_publish_update(self):
        self.store.fail_on_save = True

        with self.assertRaises(OSError):
            self.service.save(SettingsSnapshot())

        self.assertEqual(self.events, [])

    def test_clear_history_delegates_to_store(self):
        self.service.clear_history()

        self.assertTrue(self.store.history_cleared)
        self.assertEqual(self.events, ["history_cleared"])


if __name__ == "__main__":
    unittest.main()
