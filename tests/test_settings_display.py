import os
import unittest
from unittest.mock import patch

from app.settings.api_groups import APIGroup, APIGroupKey, APIGroupSettings
from app.settings.display import groups_display, settings_display
from app.settings.model import ApiKeyEntry, SettingsSnapshot


class SettingsDisplayTests(unittest.TestCase):
    def test_saved_key_uses_injected_source_without_leaking_into_repr(self):
        saved = APIGroupSettings((APIGroup(
            "g", "Group", "https://example.test/v1", "model", keys=(
                APIGroupKey("k", "Key", environment_variable="FAKE_SAVED"),
                APIGroupKey("external", "External", source="environment",
                            environment_variable="OPENAI_API_KEY"),
            ),
        ),), "g", 2)
        display = groups_display(saved, environment={
            "FAKE_SAVED": "fake-private", "OPENAI_API_KEY": "fake-external",
        })
        self.assertEqual(display.groups[0].keys[0].key, "fake-private")
        self.assertIn("留空", display.groups[0].keys[0].placeholder)
        self.assertEqual(display.groups[0].keys[1].key, "")
        self.assertNotIn("fake-private", repr(display))
        self.assertNotIn("fake-external", repr(display))
        self.assertEqual(saved.groups[0].keys[0].key, "")

    def test_snapshot_preserves_values_and_hides_legacy_keys(self):
        source = SettingsSnapshot(api_keys=(ApiKeyEntry("Key", "fake-private"),),
                                  temperature=0.753, custom_personality="  text  ")
        display = settings_display(source)
        self.assertEqual(display.temperature, 0.753)
        self.assertEqual(display.custom_personality, "  text  ")
        self.assertEqual(display.api_keys[0].key, "fake-private")
        self.assertNotIn("fake-private", repr(display))

    def test_editor_uses_supplied_values_without_reading_environment(self):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtWidgets import QApplication
        from ui.settings.widgets.api_group_editor import APIGroupEditor
        app = QApplication.instance() or QApplication([])
        source = APIGroupSettings((APIGroup(
            "g", "Group", "https://example.test/v1", "model",
            keys=(APIGroupKey("k", "Key", environment_variable="FAKE_SAVED"),),
        ),), "g", 2)
        display = groups_display(source, environment={"FAKE_SAVED": "fake-supplied"})
        editor = APIGroupEditor()
        try:
            with patch.object(os.environ, "get", side_effect=AssertionError("UI read environment")):
                editor.load_settings(display)
                raw = editor.collect_input()
            self.assertEqual(raw.groups[0].keys[0].key, "fake-supplied")
            self.assertFalse(raw.groups[0].keys[0].key_edited)
        finally:
            editor.deleteLater()
            app.processEvents()
