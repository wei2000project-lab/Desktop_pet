import os
import unittest
from dataclasses import replace
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import QApplication, QMessageBox

from app.ai.prompt_builder import get_personality_option_labels
from tests.settings_helpers import FakeSettingsBackend
from tests.settings_helpers import create_settings_window


class SettingsPersonalityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.backend = FakeSettingsBackend()
        self.window, self.presenter = create_settings_window(settings_backend=self.backend)
        self.page = self.window.personality_page

    def tearDown(self):
        self.window._close_approved = True
        self.window.close()
        self.window.deleteLater()
        self.app.processEvents()

    def test_options_match_existing_profiles_and_load_cleanly(self):
        self.assertEqual(set(self.page.personality_buttons),
                         set(get_personality_option_labels()) | {"custom"})
        self.assertTrue(self.page.personality_buttons["catgirl_companion"].isChecked())
        self.assertFalse(self.page.custom_personality_input.isEnabled())
        self.assertFalse(self.presenter.session.is_dirty)

    def test_selection_is_exclusive_and_only_updates_draft(self):
        for key, button in self.page.personality_buttons.items():
            button.click()
            self.assertEqual(sum(b.isChecked() for b in self.page.personality_buttons.values()), 1)
            self.assertEqual(self.presenter.session.snapshot.selected_personality, key)
        self.assertEqual(self.backend.saved, [])

    def test_custom_text_survives_switching_profiles_and_pages(self):
        self.page.personality_buttons["custom"].click()
        self.assertTrue(self.page.custom_personality_input.isEnabled())
        self.page.custom_personality_input.setPlainText("我的自訂人格")
        self.page.personality_buttons["warm_companion"].click()
        self.assertFalse(self.page.custom_personality_input.isEnabled())
        self.window.select_page("ai")
        self.window.select_page("personality")
        self.page.personality_buttons["custom"].click()
        self.assertEqual(self.page.custom_personality_input.toPlainText(), "我的自訂人格")

    def test_all_pages_save_together_and_reload_normalized_text(self):
        self.page.personality_buttons["custom"].click()
        self.page.custom_personality_input.setPlainText("  我的自訂人格  ")
        self.window.general_page.always_on_top_check.setChecked(True)
        self.window.appearance_page.width_input.setValue(400)
        self.window.behavior_page.reading_idle_seconds_input.setValue(120)
        self.window.ai_page.model_input.setText("test-model")
        self.assertTrue(self.presenter.apply_changes())
        saved = self.backend.saved[0]
        self.assertEqual(saved.selected_personality, "custom")
        self.assertEqual(saved.custom_personality, "我的自訂人格")
        self.assertTrue(saved.always_on_top)
        self.assertEqual(saved.width, 400)
        self.assertEqual(saved.reading_idle_seconds, 120)
        self.assertEqual(saved.model, "test-model")
        self.assertEqual(self.page.custom_personality_input.toPlainText(), "我的自訂人格")
        self.assertFalse(self.presenter.session.is_dirty)

    def test_cancel_restores_selection_and_text(self):
        self.page.personality_buttons["custom"].click()
        self.page.custom_personality_input.setPlainText("不儲存")
        self.presenter.cancel_changes()
        self.assertTrue(self.page.personality_buttons["catgirl_companion"].isChecked())
        self.assertEqual(self.page.custom_personality_input.toPlainText(), "")
        self.assertFalse(self.page.custom_personality_input.isEnabled())
        self.assertEqual(self.backend.saved, [])

    def test_reverting_selection_clears_dirty_state(self):
        self.page.personality_buttons["warm_companion"].click()
        self.page.personality_buttons["catgirl_companion"].click()
        self.assertFalse(self.presenter.session.is_dirty)

    def test_discard_close_restores_personality(self):
        self.page.personality_buttons["custom"].click()
        self.page.custom_personality_input.setPlainText("不儲存")
        event = QCloseEvent()
        with patch("ui.settings.settings_window.SettingsDialog.question",
                   return_value=QMessageBox.StandardButton.Discard):
            self.window.closeEvent(event)
        self.assertTrue(event.isAccepted())
        self.assertFalse(self.presenter.session.is_dirty)
        self.assertTrue(self.page.personality_buttons["catgirl_companion"].isChecked())

    def test_loading_empty_or_unknown_selection_does_not_overwrite_it(self):
        for selected in ("", "unknown-profile", "custom"):
            snapshot = replace(self.backend.snapshot, selected_personality=selected,
                               custom_personality="保留內容")
            self.presenter.session.original_snapshot = snapshot
            self.presenter.session.snapshot = snapshot
            self.window.load_snapshot(snapshot)
            self.assertFalse(self.presenter.session.is_dirty)
            self.assertEqual(self.presenter.session.snapshot.selected_personality, selected)
            self.assertEqual(self.page.custom_personality_input.isEnabled(), selected == "custom")


if __name__ == "__main__":
    unittest.main()
