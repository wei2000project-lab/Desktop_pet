from app.settings.editing import groups_from_input
from app.settings.display import groups_display
"""Characterize source switching before moving editor rules out of the UI."""
import os
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication
from app.settings.api_groups import APIGroup, APIGroupKey, APIGroupSettings
from ui.settings.widgets.api_group_editor import APIGroupEditor


class SettingsSourceBaselineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.editor = APIGroupEditor()

    def tearDown(self):
        self.editor.deleteLater()
        self.app.processEvents()

    def load_key(self, entry):
        settings = APIGroupSettings((APIGroup(
            "group", "Example", "https://example.test/v1", "model", keys=(entry,),
        ),), "group", 2)
        self.baseline = settings
        self.editor.load_settings(groups_display(settings))
        return self.editor.group_rows[0]["keys"][0]

    def test_saved_source_round_trip_preserves_reference_and_unchanged_value(self):
        with patch.dict(os.environ, {"NOVA_BASELINE_FAKE": "fake-saved"}):
            row = self.load_key(APIGroupKey(
                "key", "Key", environment_variable="NOVA_BASELINE_FAKE",
            ))
        row["source"].setCurrentIndex(row["source"].findData("environment"))
        switched = groups_from_input(self.editor.collect_input(), self.baseline).groups[0].keys[0]
        self.assertEqual(switched.environment_variable, "OPENAI_API_KEY")
        self.assertEqual(switched.key, "")
        row["source"].setCurrentIndex(row["source"].findData("stored"))
        restored = groups_from_input(self.editor.collect_input(), self.baseline).groups[0].keys[0]
        self.assertEqual(restored.environment_variable, "NOVA_BASELINE_FAKE")
        self.assertEqual(restored.key, "")

    def test_environment_to_stored_does_not_reuse_external_reference(self):
        row = self.load_key(APIGroupKey(
            "key", "Key", source="environment", environment_variable="OPENAI_API_KEY",
        ))
        row["source"].setCurrentIndex(row["source"].findData("stored"))
        row["key"].setText("fake-replacement")
        changed = groups_from_input(self.editor.collect_input(), self.baseline).groups[0].keys[0]
        self.assertEqual(changed.source, "stored")
        self.assertEqual(changed.environment_variable, "")
        self.assertEqual(changed.key, "fake-replacement")
