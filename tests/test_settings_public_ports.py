from app.settings.display import groups_display
"""Public component boundaries remain usable without exposing widget rows."""
import os
import unittest
from dataclasses import FrozenInstanceError, fields
from types import SimpleNamespace
from unittest.mock import Mock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QBoxLayout
from app.contracts.settings import (
    APIGroupDisplay, APIGroupInput, APIKeyDisplay, APIKeyInput,
    APIGroupsInput, ConnectionInputs, GroupTestInputs,
)
from app.settings.api_groups import APIGroup, APIGroupKey, APIGroupSettings
from ui.settings import SettingsWindow
from ui.settings.pages.ai_page import AIPage
from ui.settings.widgets.api_group_editor import APIGroupEditor


class SettingsPublicPortsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def widget(self, factory):
        widget = factory()
        self.addCleanup(self.dispose, widget)
        return widget

    def dispose(self, widget):
        widget.close()
        widget.deleteLater()
        self.app.processEvents()

    @staticmethod
    def groups():
        return APIGroupSettings((APIGroup(
            "group", "Example", "https://example.test/v1", "model",
            keys=(APIGroupKey("key", "Key", "fake-value"),),
        ),), "group")

    def test_window_accepts_page_port_without_any_row_structure(self):
        window = self.widget(SettingsWindow)
        expected = ConnectionInputs({12: "fake-key"}, 7, frozenset({("group", "key")}))
        with patch.object(window, "ai_page", SimpleNamespace(connection_inputs=lambda: expected)):
            self.assertIs(window.connection_inputs(), expected)

    def test_page_accepts_editor_port_and_returns_detached_legacy_values(self):
        page = self.widget(AIPage)
        row = page.add_api_key_row("Key", "fake-first")
        expected = GroupTestInputs(9, frozenset({("other", "")}))
        with patch.object(page, "group_editor", SimpleNamespace(connection_inputs=lambda: expected)):
            snapshot = page.connection_inputs()
        row["key_input"].setText("fake-second")
        self.assertEqual(snapshot.legacy_keys, {row["id"]: "fake-first"})
        self.assertEqual(snapshot.group_generation, 9)
        self.assertEqual(snapshot.group_targets, expected.targets)

    def test_targets_track_deletion_and_rebuild_without_mutating_old_snapshot(self):
        editor = self.widget(APIGroupEditor)
        editor.load_settings(groups_display(self.groups()))
        before = editor.connection_inputs()
        self.assertEqual(before.targets, frozenset({("group", ""), ("group", "key")}))
        editor.remove_key("group", "key")
        self.assertEqual(editor.connection_inputs().targets, frozenset({("group", "")}))
        self.assertIn(("group", "key"), before.targets)
        editor.load_settings(groups_display(self.groups()))
        self.assertGreater(editor.connection_inputs().generation, before.generation)

    def test_raw_input_preserves_text_and_reports_changes_without_storage_rules(self):
        editor = self.widget(APIGroupEditor)
        editor.load_settings(groups_display(self.groups()))
        before = editor.collect_input()
        self.assertIsInstance(before, APIGroupsInput)
        self.assertFalse(before.groups[0].keys[0].key_edited)
        self.assertFalse(before.groups[0].temperature_edited)
        row = editor.group_rows[0]
        key = row["keys"][0]
        key["key"].setText("  fake-new  ")
        key["name"].setText("  new name  ")
        key["source"].setCurrentIndex(key["source"].findData("environment"))
        row["temperature"].setValue(1.25)
        value = editor.collect_input()
        self.assertEqual(value.groups[0].keys[0].key, "  fake-new  ")
        self.assertEqual(value.groups[0].keys[0].name, "  new name  ")
        self.assertTrue(value.groups[0].keys[0].key_edited)
        self.assertTrue(value.groups[0].temperature_edited)
        self.assertEqual(before.groups[0].keys[0].key, "fake-value")
        with self.assertRaises(FrozenInstanceError):
            value.active_group_id = None
        key["key"].setText("fake-value")
        self.assertFalse(editor.collect_input().groups[0].keys[0].key_edited)
        key["key"].clear()
        self.assertEqual(editor.collect_input().groups[0].keys[0].key, "")
        self.assertTrue(editor.collect_input().groups[0].keys[0].key_edited)

    def test_group_contracts_omit_storage_metadata_and_hide_secret_repr(self):
        for contract in (APIGroupDisplay, APIGroupInput, APIKeyDisplay, APIKeyInput):
            names = {item.name for item in fields(contract)}
            self.assertNotIn("schema_version", names)
            self.assertNotIn("environment_variable", names)
        value = APIKeyInput("key", "Key", "fake-sensitive", 1, True, "stored", False)
        display = APIKeyDisplay("key", "Key", "fake-sensitive", 1, True, "stored")
        self.assertNotIn("fake-sensitive", repr(value))
        self.assertNotIn("fake-sensitive", repr(display))
        self.assertNotIn("fake-sensitive", repr(ConnectionInputs({1: "fake-sensitive"})))

    def test_page_resize_uses_public_width_port(self):
        page = self.widget(AIPage)
        port = SimpleNamespace(set_available_width=Mock())
        with patch.object(page, "group_editor", port):
            page.resize(730, 500)
            page.show()
            self.app.processEvents()
            port.set_available_width.assert_called()
            self.assertTrue(all(call.args[0] >= 0 for call in port.set_available_width.call_args_list))

    def test_public_width_port_keeps_responsive_behavior(self):
        editor = self.widget(APIGroupEditor)
        editor.load_settings(groups_display(self.groups()))
        editor.set_available_width(450)
        self.assertEqual(editor.master_detail_layout.direction(), QBoxLayout.TopToBottom)
        editor.set_available_width(800)
        self.assertEqual(editor.master_detail_layout.direction(), QBoxLayout.LeftToRight)
