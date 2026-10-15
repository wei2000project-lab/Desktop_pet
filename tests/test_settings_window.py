import os
import pathlib
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtGui import QCloseEvent
from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QAbstractSpinBox
from PySide6.QtWidgets import QApplication, QMessageBox, QScrollArea

from app.settings import ApiKeyEntry, SettingsValidationError
from dataclasses import replace
from tests.settings_helpers import FakeSettingsBackend
from tests.settings_helpers import create_settings_window
from ui.settings.widgets.input_controls import ToggleSwitch
from ui.settings.page_registry import default_page_definitions


class SettingsWindowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.settings = FakeSettingsBackend()
        self.window, self.presenter = create_settings_window(settings_backend=self.settings)

    def tearDown(self):
        self.window._close_approved = True
        self.window.close()
        self.window.deleteLater()
        self.app.processEvents()

    def test_button_feedback_returns_to_normal_after_focus(self):
        self.window.show()
        self.app.processEvents()
        button = self.window.cancel_button

        def background():
            self.app.processEvents()
            return button.grab().toImage().pixelColor(8, button.height() // 2).name()

        normal = background()
        QTest.mouseMove(button, QPoint(8, button.height() // 2))
        hover = background()
        QTest.mousePress(button, Qt.LeftButton, pos=QPoint(8, button.height() // 2))
        pressed = background()
        QTest.mouseRelease(button, Qt.LeftButton, pos=QPoint(-8, -8))
        QTest.mouseMove(self.window, QPoint(self.window.width() - 2, self.window.height() - 2))

        self.assertNotEqual(hover, normal)
        self.assertNotEqual(pressed, hover)
        self.assertTrue(button.hasFocus())
        self.assertEqual(background(), normal)

        selected = self.window.sidebar.button_for_key("general")
        self.assertTrue(selected.isChecked())
        selected_background = selected.grab().toImage().pixelColor(8, selected.height() // 2).name()
        QTest.mouseMove(selected, QPoint(8, selected.height() // 2))
        self.app.processEvents()
        self.assertNotEqual(
            selected.grab().toImage().pixelColor(8, selected.height() // 2).name(),
            selected_background,
        )
        QTest.mouseMove(self.window, QPoint(self.window.width() - 2, self.window.height() - 2))
        self.app.processEvents()
        self.assertEqual(
            selected.grab().toImage().pixelColor(8, selected.height() // 2).name(),
            selected_background,
        )

    def test_default_registry_has_unique_ordered_pages(self):
        pages = default_page_definitions()

        self.assertEqual(
            [page.key for page in pages],
            ["general", "appearance", "behavior", "ai", "personality"],
        )
        self.assertEqual(len({page.key for page in pages}), len(pages))


    def test_sidebar_and_content_are_built_from_same_registry(self):
        self.assertEqual(
            self.window.content_stack.count(), len(self.window.page_definitions)
        )
        for definition in self.window.page_definitions:
            self.assertIsNotNone(self.window.sidebar.button_for_key(definition.key))
            page = self.window.page_for_key(definition.key)
            self.assertIsInstance(page, QScrollArea)
            self.assertTrue(page.widgetResizable())


    def test_pages_do_not_persist_settings_directly(self):
        source = "\n".join(
            path.read_text(encoding="utf-8")
            for path in pathlib.Path("ui/settings/pages").rglob("*.py")
        )

        self.assertNotIn("settings_service", source)
        self.assertNotIn("config_manager", source)

    def test_general_change_stays_in_draft_until_apply(self):
        self.assertFalse(self.window.general_page.always_on_top_check.isChecked())
        self.assertFalse(self.window.apply_button.isEnabled())

        self.window.general_page.always_on_top_check.setChecked(True)
        self.window.select_page("ai")

        self.assertTrue(self.presenter.session.is_dirty)
        self.assertTrue(self.window.apply_button.isEnabled())
        self.assertEqual(self.settings.saved, [])

        self.assertTrue(self.presenter.apply_changes())
        self.assertFalse(self.presenter.session.is_dirty)
        self.assertEqual(len(self.settings.saved), 1)
        self.assertTrue(self.settings.saved[0].always_on_top)

    def test_general_page_uses_unified_toggle_and_danger_hierarchy(self):
        page = self.window.general_page

        self.assertIsInstance(page.always_on_top_check, ToggleSwitch)
        self.assertEqual(page.always_on_top_status.text(), "已停用")
        self.assertFalse(page.always_on_top_status.property("active"))
        self.assertEqual(
            page.clear_history_button.parentWidget().objectName(),
            "settingsDangerCard",
        )

        page.always_on_top_check.setChecked(True)

        self.assertEqual(page.always_on_top_status.text(), "已啟用")
        self.assertTrue(page.always_on_top_status.property("active"))
        self.assertTrue(self.presenter.session.is_dirty)

    def test_cancel_restores_original_value_without_saving(self):
        self.window.general_page.always_on_top_check.setChecked(True)

        self.presenter.cancel_changes()

        self.assertFalse(self.window.general_page.always_on_top_check.isChecked())
        self.assertEqual(self.settings.saved, [])

    def test_clear_history_requires_confirmation(self):
        with (
            patch(
                "ui.settings.settings_window.SettingsDialog.question",
                return_value=QMessageBox.StandardButton.Yes,
            ),
            patch("ui.settings.settings_window.SettingsDialog.information"),
        ):
            self.window.general_page.clear_history_button.click()

        self.assertEqual(self.settings.history_clear_count, 1)

    def test_appearance_loads_without_dirtying_settings(self):
        page = self.window.appearance_page
        self.assertEqual(page.width_input.value(), self.settings.snapshot.width)
        self.assertEqual(page.height_input.value(), self.settings.snapshot.height)
        self.assertFalse(self.presenter.session.is_dirty)

    def test_size_controls_enforce_range_and_step(self):
        for control in (self.window.appearance_page.width_input,
                        self.window.appearance_page.height_input):
            self.assertEqual(control.singleStep(), 10)
            control.setValue(1)
            self.assertEqual(control.value(), 100)
            control.setValue(2000)
            self.assertEqual(control.value(), 1000)

    def test_cross_page_changes_save_together(self):
        page = self.window.appearance_page
        page.width_input.setValue(400)
        page.height_input.setValue(350)
        self.window.select_page("general")
        self.window.general_page.always_on_top_check.setChecked(True)
        self.window.select_page("appearance")
        self.assertEqual(page.width_input.value(), 400)
        self.assertEqual(self.settings.saved, [])
        self.assertTrue(self.presenter.apply_changes())
        saved = self.settings.saved[0]
        self.assertEqual((saved.width, saved.height), (400, 350))
        self.assertTrue(saved.always_on_top)
        self.assertFalse(self.presenter.session.is_dirty)

    def test_cancel_restores_both_pages(self):
        self.window.appearance_page.width_input.setValue(500)
        self.window.general_page.always_on_top_check.setChecked(True)
        self.presenter.cancel_changes()
        self.assertEqual(self.window.appearance_page.width_input.value(),
                         self.settings.snapshot.width)
        self.assertFalse(self.presenter.session.is_dirty)
        self.assertEqual(self.settings.saved, [])

    def test_reverting_size_clears_dirty_state(self):
        control = self.window.appearance_page.width_input
        control.setValue(500)
        control.setValue(self.settings.snapshot.width)
        self.assertFalse(self.presenter.session.is_dirty)
        self.assertFalse(self.window.apply_button.isEnabled())

    def test_save_failure_preserves_size_draft(self):
        self.window.appearance_page.width_input.setValue(500)
        with (
            patch.object(self.settings, "save", side_effect=SettingsValidationError("無效尺寸")),
            patch("ui.settings.settings_window.SettingsDialog.warning"),
        ):
            self.assertFalse(self.presenter.apply_changes())
        self.assertTrue(self.presenter.session.is_dirty)
        self.assertEqual(self.window.appearance_page.width_input.value(), 500)

    def test_discarding_close_restores_size(self):
        self.window.appearance_page.width_input.setValue(500)
        event = QCloseEvent()
        with patch("ui.settings.settings_window.SettingsDialog.question",
                   return_value=QMessageBox.StandardButton.Discard):
            self.window.closeEvent(event)
        self.assertTrue(event.isAccepted())
        self.assertEqual(self.window.appearance_page.width_input.value(),
                         self.settings.snapshot.width)
        self.assertEqual(self.settings.saved, [])

    def test_discarding_close_restores_original_draft(self):
        self.window.general_page.always_on_top_check.setChecked(True)
        event = QCloseEvent()
        with patch(
            "ui.settings.settings_window.SettingsDialog.question",
            return_value=QMessageBox.StandardButton.Discard,
        ):
            self.window.closeEvent(event)

        self.assertTrue(event.isAccepted())
        self.assertFalse(self.presenter.session.is_dirty)
        self.assertFalse(self.window.general_page.always_on_top_check.isChecked())
        self.assertEqual(self.settings.saved, [])

    def test_behavior_loads_without_dirtying_settings(self):
        control = self.window.behavior_page.reading_idle_seconds_input
        self.assertEqual(control.value(), self.settings.snapshot.reading_idle_seconds)
        self.assertFalse(self.presenter.session.is_dirty)
        self.assertEqual(self.settings.saved, [])

    def test_behavior_enforces_range_and_step(self):
        control = self.window.behavior_page.reading_idle_seconds_input
        self.assertEqual(control.singleStep(), 10)
        control.setValue(0)
        self.assertEqual(control.value(), 10)
        control.setValue(4000)
        self.assertEqual(control.value(), 3600)

    def test_three_page_changes_save_together(self):
        control = self.window.behavior_page.reading_idle_seconds_input
        control.setValue(120)
        self.window.select_page("appearance")
        self.window.appearance_page.width_input.setValue(400)
        self.window.select_page("general")
        self.window.general_page.always_on_top_check.setChecked(True)
        self.window.select_page("behavior")
        self.assertEqual(control.value(), 120)
        self.assertEqual(self.settings.saved, [])
        self.assertTrue(self.presenter.apply_changes())
        saved = self.settings.saved[0]
        self.assertEqual(saved.reading_idle_seconds, 120)
        self.assertEqual(saved.width, 400)
        self.assertTrue(saved.always_on_top)
        self.assertFalse(self.presenter.session.is_dirty)

    def test_cancel_restores_behavior_without_saving(self):
        control = self.window.behavior_page.reading_idle_seconds_input
        control.setValue(120)
        self.presenter.cancel_changes()
        self.assertEqual(control.value(), self.settings.snapshot.reading_idle_seconds)
        self.assertFalse(self.presenter.session.is_dirty)
        self.assertEqual(self.settings.saved, [])

    def test_reverting_behavior_clears_dirty_state(self):
        control = self.window.behavior_page.reading_idle_seconds_input
        control.setValue(120)
        control.setValue(self.settings.snapshot.reading_idle_seconds)
        self.assertFalse(self.presenter.session.is_dirty)
        self.assertFalse(self.window.apply_button.isEnabled())

    def test_failed_behavior_save_preserves_draft(self):
        control = self.window.behavior_page.reading_idle_seconds_input
        control.setValue(120)
        with (
            patch.object(self.settings, "save", side_effect=SettingsValidationError("無效秒數")),
            patch("ui.settings.settings_window.SettingsDialog.warning"),
        ):
            self.assertFalse(self.presenter.apply_changes())
        self.assertEqual(control.value(), 120)
        self.assertTrue(self.presenter.session.is_dirty)
        self.assertEqual(self.settings.saved, [])

    def test_dirty_behavior_close_cancel_preserves_draft(self):
        self.window.behavior_page.reading_idle_seconds_input.setValue(120)
        event = QCloseEvent()
        with patch("ui.settings.settings_window.SettingsDialog.question",
                   return_value=QMessageBox.StandardButton.Cancel):
            self.window.closeEvent(event)
        self.assertFalse(event.isAccepted())
        self.assertTrue(self.presenter.session.is_dirty)

    def test_dirty_behavior_close_discard_restores_value(self):
        control = self.window.behavior_page.reading_idle_seconds_input
        control.setValue(120)
        event = QCloseEvent()
        with patch("ui.settings.settings_window.SettingsDialog.question",
                   return_value=QMessageBox.StandardButton.Discard):
            self.window.closeEvent(event)
        self.assertTrue(event.isAccepted())
        self.assertEqual(control.value(), self.settings.snapshot.reading_idle_seconds)
        self.assertFalse(self.presenter.session.is_dirty)
        self.assertEqual(self.settings.saved, [])

    def test_dirty_behavior_close_save_persists_value(self):
        self.window.behavior_page.reading_idle_seconds_input.setValue(120)
        event = QCloseEvent()
        with patch("ui.settings.settings_window.SettingsDialog.question",
                   return_value=QMessageBox.StandardButton.Save):
            self.window.closeEvent(event)
        self.assertTrue(event.isAccepted())
        self.assertEqual(self.settings.saved[0].reading_idle_seconds, 120)
        self.assertFalse(self.presenter.session.is_dirty)


    def test_ai_loads_without_dirtying_settings(self):
        page = self.window.ai_page
        self.assertEqual(page.base_url_input.text(), self.settings.snapshot.base_url)
        self.assertEqual(page.model_input.text(), self.settings.snapshot.model)
        self.assertEqual(page.temperature_input.value(), 0.7)
        self.assertEqual(page.max_memory_turns_input.value(), 6)
        self.assertEqual(page.history_limit_input.value(), 20)
        self.assertTrue(page.conversation_summary_check.isChecked())
        self.assertFalse(self.presenter.session.is_dirty)

    def test_ai_numeric_ranges(self):
        page = self.window.ai_page
        for control, low, high in (
            (page.temperature_input, 0.0, 2.0),
            (page.max_memory_turns_input, 0, 50),
            (page.history_limit_input, 1, 100),
        ):
            control.setValue(-10)
            self.assertEqual(control.value(), low)
            control.setValue(1000)
            self.assertEqual(control.value(), high)
        self.assertAlmostEqual(page.temperature_input.singleStep(), 0.1)

    def test_ai_and_other_pages_save_together_preserving_keys(self):
        snapshot = replace(self.settings.snapshot,
                           api_keys=(ApiKeyEntry("test", "fake-test-key"),),
                           verify_ssl=False, custom_personality="保留人格")
        self.presenter.session.original_snapshot = snapshot
        self.presenter.session.snapshot = snapshot
        self.window.load_snapshot(snapshot)
        page = self.window.ai_page
        page.base_url_input.setText(" https://example.test/v1 ")
        page.model_input.setText(" test-model ")
        page.temperature_input.setValue(1.2)
        page.max_memory_turns_input.setValue(10)
        page.history_limit_input.setValue(30)
        page.conversation_summary_check.setChecked(False)
        self.window.select_page("appearance")
        self.window.appearance_page.width_input.setValue(400)
        self.window.behavior_page.reading_idle_seconds_input.setValue(120)
        self.window.general_page.always_on_top_check.setChecked(True)
        self.window.select_page("ai")
        self.assertEqual(page.model_input.text(), " test-model ")
        self.assertEqual(self.settings.saved, [])
        self.assertTrue(self.presenter.apply_changes())
        saved = self.settings.saved[0]
        self.assertEqual(saved.base_url, "https://example.test/v1")
        self.assertEqual(saved.model, "test-model")
        self.assertEqual(saved.temperature, 1.2)
        self.assertEqual(saved.max_memory_turns, 10)
        self.assertEqual(saved.history_limit, 30)
        self.assertFalse(saved.conversation_summary_enabled)
        self.assertEqual(saved.width, 400)
        self.assertEqual(saved.reading_idle_seconds, 120)
        self.assertTrue(saved.always_on_top)
        self.assertEqual(saved.api_keys, snapshot.api_keys)
        self.assertEqual(saved.verify_ssl, snapshot.verify_ssl)
        self.assertEqual(saved.custom_personality, snapshot.custom_personality)
        self.assertEqual(page.model_input.text(), "test-model")
        self.assertFalse(self.presenter.session.is_dirty)

    def test_ai_invalid_text_preserves_draft(self):
        for field, value in (("base_url_input", "bad-url"),
                             ("base_url_input", ""), ("model_input", "   ")):
            with self.subTest(field=field, value=value):
                self.presenter.discard()
                getattr(self.window.ai_page, field).setText(value)
                with patch("ui.settings.settings_window.SettingsDialog.warning") as warning:
                    self.assertFalse(self.presenter.apply_changes())
                    warning.assert_called_once()
                self.assertTrue(self.presenter.session.is_dirty)
                self.assertEqual(getattr(self.window.ai_page, field).text(), value)
                self.assertEqual(self.settings.saved, [])

    def test_cancel_restores_ai_fields(self):
        page = self.window.ai_page
        page.model_input.setText("changed")
        page.temperature_input.setValue(1.5)
        page.conversation_summary_check.setChecked(False)
        self.presenter.cancel_changes()
        self.assertEqual(page.model_input.text(), self.settings.snapshot.model)
        self.assertEqual(page.temperature_input.value(), 0.7)
        self.assertTrue(page.conversation_summary_check.isChecked())
        self.assertFalse(self.presenter.session.is_dirty)
        self.assertEqual(self.settings.saved, [])

    def test_reverting_ai_field_clears_dirty_state(self):
        page = self.window.ai_page
        page.model_input.setText("changed")
        page.model_input.setText(self.settings.snapshot.model)
        self.assertFalse(self.window.apply_button.isEnabled())

    def test_close_save_with_invalid_ai_keeps_window_open(self):
        self.window.ai_page.model_input.setText("")
        event = QCloseEvent()
        with (
            patch("ui.settings.settings_window.SettingsDialog.question",
                  return_value=QMessageBox.StandardButton.Save),
            patch("ui.settings.settings_window.SettingsDialog.warning"),
        ):
            self.window.closeEvent(event)
        self.assertFalse(event.isAccepted())
        self.assertTrue(self.presenter.session.is_dirty)

    def test_all_numeric_controls_have_clickable_separate_buttons(self):
        self.window.show()
        self.window.resize(650, 600)
        controls = (
            ("appearance", self.window.appearance_page.width_input, 300),
            ("appearance", self.window.appearance_page.height_input, 300),
            ("behavior", self.window.behavior_page.reading_idle_seconds_input, 300),
            ("ai", self.window.ai_page.temperature_input, 0.7),
            ("ai", self.window.ai_page.max_memory_turns_input, 6),
            ("ai", self.window.ai_page.history_limit_input, 20),
        )
        for page_key, control, initial in controls:
            with self.subTest(page=page_key, control=control.accessibleName()):
                self.window.select_page(page_key)
                page = self.window.content_stack.currentWidget()
                page.ensureWidgetVisible(control)
                control.setValue(initial)
                self.app.processEvents()
                self.assertEqual(control.editor.buttonSymbols(), QAbstractSpinBox.NoButtons)
                self.assertFalse(control.editor.geometry().intersects(control.plus_button.geometry()))
                self.assertFalse(control.editor.geometry().intersects(control.minus_button.geometry()))
                QTest.mouseClick(control.plus_button, Qt.LeftButton)
                self.assertAlmostEqual(control.value(), initial + control.singleStep())
                QTest.mouseClick(control.minus_button, Qt.LeftButton)
                self.assertAlmostEqual(control.value(), initial)

    def test_numeric_buttons_disable_at_bounds(self):
        control = self.window.appearance_page.width_input
        control.setValue(control.minimum())
        self.assertFalse(control.minus_button.isEnabled())
        self.assertTrue(control.plus_button.isEnabled())
        control.setValue(control.maximum())
        self.assertTrue(control.minus_button.isEnabled())
        self.assertFalse(control.plus_button.isEnabled())

    def test_numeric_input_still_accepts_keyboard_editing(self):
        control = self.window.appearance_page.width_input
        editor = control.editor
        editor.setFocus()
        editor.selectAll()
        QTest.keyClicks(editor, "420")
        QTest.keyClick(editor, Qt.Key_Return)
        self.assertEqual(control.value(), 420)
        self.assertTrue(self.presenter.session.is_dirty)
        self.assertTrue(self.presenter.apply_changes())
        self.assertEqual(self.settings.saved[0].width, 420)

if __name__ == "__main__":
    unittest.main()
