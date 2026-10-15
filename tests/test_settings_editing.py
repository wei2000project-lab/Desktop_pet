import unittest
from dataclasses import replace

from app.contracts.settings import APIGroupInput, APIKeyInput, APIGroupsInput
from app.settings.api_groups import APIGroup, APIGroupKey, APIGroupSettings
from app.settings.editing import groups_from_input, normalize_group_input


class SettingsEditingTests(unittest.TestCase):
    def setUp(self):
        self.baseline = APIGroupSettings((APIGroup(
            "g", "Group", "https://example.test/v1", "model", temperature=0.753,
            keys=(APIGroupKey("k", "Key", environment_variable="FAKE_SAVED"),),
        ),), "g", 2)
        self.raw_key = APIKeyInput("k", "Key", "fake-display", 1, True, "stored", False)

    def form(self, key, **changes):
        group = APIGroupInput("g", "Group", "https://example.test/v1", "model", 0.75,
                              True, "api_key", (key,), False)
        return APIGroupsInput((replace(group, **changes),), "g")

    def convert(self, key, **changes):
        return normalize_group_input(groups_from_input(self.form(key, **changes), self.baseline))

    def test_unchanged_display_and_precision_preserve_storage_baseline(self):
        result = self.convert(self.raw_key, name="Renamed")
        self.assertEqual(result.groups[0].keys[0].key, "")
        self.assertEqual(result.groups[0].keys[0].environment_variable, "FAKE_SAVED")
        self.assertEqual(result.groups[0].temperature, 0.753)
        edited = self.convert(self.raw_key, temperature=1.25, temperature_edited=True)
        self.assertEqual(edited.groups[0].temperature, 1.25)

    def test_blank_preserves_reference_and_changed_key_is_normalized(self):
        blank = self.convert(replace(self.raw_key, key="  ", key_edited=True))
        self.assertEqual(blank, self.baseline)
        replaced = self.convert(replace(self.raw_key, key=" fake-new ", key_edited=True))
        self.assertEqual(replaced.groups[0].keys[0].key, "fake-new")
        self.assertEqual(replaced.groups[0].keys[0].environment_variable, "FAKE_SAVED")

    def test_source_round_trip_is_based_on_original_source(self):
        switched = self.convert(replace(self.raw_key, source="environment"))
        self.assertEqual(switched.groups[0].keys[0].environment_variable, "OPENAI_API_KEY")
        self.assertEqual(switched.groups[0].keys[0].key, "")
        self.assertEqual(self.convert(self.raw_key), self.baseline)

    def test_empty_new_row_is_omitted_and_removed_saved_row_is_absent(self):
        new = APIKeyInput("new", "", "", 1, True, "stored", False)
        result = self.convert(self.raw_key, keys=(self.raw_key, new))
        self.assertEqual(result, self.baseline)
        removed = self.convert(self.raw_key, keys=())
        self.assertEqual(removed.groups[0].keys, ())
