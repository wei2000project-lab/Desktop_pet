import os
import pathlib
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import QApplication, QMessageBox, QScrollArea

from app.settings import SettingsSnapshot, SettingsValidationError
from ui.dashboard import DashboardWindow
from ui.dashboard.page_registry import default_page_definitions
from ui.dashboard.sidebar import DashboardSidebar


class FakeSettingsBackend:
    def __init__(self):
        self.snapshot = SettingsSnapshot(always_on_top=False)
        self.saved = []
        self.history_clear_count = 0

    def load(self):
        return self.snapshot

    def save(self, snapshot):
        self.saved.append(snapshot)
        self.snapshot = snapshot
        return snapshot

    def clear_history(self):
        self.history_clear_count += 1


class DashboardShellTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.settings = FakeSettingsBackend()
        self.window = DashboardWindow(settings_backend=self.settings)

    def tearDown(self):
        self.window._allow_close = True
        self.window.close()
        self.window.deleteLater()
        self.app.processEvents()

    def test_default_registry_has_unique_ordered_pages(self):
        pages = default_page_definitions()

        self.assertEqual(
            [page.key for page in pages],
            ["general", "appearance", "behavior", "ai", "personality"],
        )
        self.assertEqual(len({page.key for page in pages}), len(pages))

    def test_window_uses_expected_default_and_minimum_size(self):
        self.assertEqual(self.window.size().width(), 900)
        self.assertEqual(self.window.size().height(), 760)
        self.assertEqual(self.window.minimumWidth(), 650)
        self.assertEqual(self.window.minimumHeight(), 600)

    def test_sidebar_and_content_are_built_from_same_registry(self):
        self.assertEqual(
            self.window.content_stack.count(), len(self.window.page_definitions)
        )
        for definition in self.window.page_definitions:
            self.assertIsNotNone(self.window.sidebar.button_for_key(definition.key))
            page = self.window.content_stack.widget(
                self.window._page_indexes[definition.key]
            )
            self.assertIsInstance(page, QScrollArea)
            self.assertTrue(page.widgetResizable())

    def test_navigation_selects_matching_page_and_button(self):
        button = self.window.sidebar.button_for_key("ai")
        button.click()

        self.assertEqual(self.window.current_page_key, "ai")
        self.assertTrue(button.isChecked())

    def test_sidebar_collapsed_state_keeps_tooltips_and_selection(self):
        self.window.select_page("personality")
        self.window.sidebar.set_collapsed(True)

        button = self.window.sidebar.button_for_key("personality")
        self.assertTrue(self.window.sidebar.is_collapsed)
        self.assertEqual(self.window.sidebar.width(), DashboardSidebar.COLLAPSED_WIDTH)
        self.assertEqual(button.text(), "")
        self.assertEqual(button.toolTip(), "人格")
        self.assertTrue(button.isChecked())

        self.window.sidebar.set_collapsed(False)
        self.assertEqual(self.window.sidebar.width(), DashboardSidebar.EXPANDED_WIDTH)
        self.assertEqual(button.text(), "人格")

    def test_entering_narrow_width_auto_collapses_but_manual_toggle_still_works(self):
        self.window.show()
        self.app.processEvents()
        self.window.resize(700, 600)
        self.app.processEvents()

        self.assertTrue(self.window.sidebar.is_collapsed)
        self.window.sidebar.toggle_button.click()
        self.assertFalse(self.window.sidebar.is_collapsed)

    def test_manual_collapsed_preference_survives_narrow_round_trip(self):
        self.window.show()
        self.app.processEvents()
        self.window.sidebar.set_collapsed(True)
        self.window.resize(700, 600)
        self.app.processEvents()
        self.window.resize(900, 650)
        self.app.processEvents()

        self.assertTrue(self.window.sidebar.is_collapsed)

    def test_unknown_page_is_rejected(self):
        with self.assertRaises(KeyError):
            self.window.select_page("missing")

    def test_pages_do_not_persist_settings_directly(self):
        source = "\n".join(
            path.read_text(encoding="utf-8")
            for path in pathlib.Path("ui/dashboard/pages").rglob("*.py")
        )

        self.assertNotIn("settings_service", source)
        self.assertNotIn("config_manager", source)

    def test_general_change_stays_in_draft_until_apply(self):
        self.assertFalse(self.window.general_page.always_on_top_check.isChecked())
        self.assertFalse(self.window.apply_button.isEnabled())

        self.window.general_page.always_on_top_check.setChecked(True)
        self.window.select_page("ai")

        self.assertTrue(self.window.is_dirty)
        self.assertTrue(self.window.apply_button.isEnabled())
        self.assertEqual(self.settings.saved, [])

        self.assertTrue(self.window.apply_changes())
        self.assertFalse(self.window.is_dirty)
        self.assertEqual(len(self.settings.saved), 1)
        self.assertTrue(self.settings.saved[0].always_on_top)

    def test_cancel_restores_original_value_without_saving(self):
        self.window.general_page.always_on_top_check.setChecked(True)

        self.window.cancel_changes()

        self.assertFalse(self.window.general_page.always_on_top_check.isChecked())
        self.assertEqual(self.settings.saved, [])

    def test_clear_history_requires_confirmation(self):
        with (
            patch(
                "ui.dashboard.dashboard_window.QMessageBox.question",
                return_value=QMessageBox.StandardButton.Yes,
            ),
            patch("ui.dashboard.dashboard_window.QMessageBox.information"),
        ):
            self.window.general_page.clear_history_button.click()

        self.assertEqual(self.settings.history_clear_count, 1)

    def test_appearance_loads_without_dirtying_settings(self):
        page = self.window.appearance_page
        self.assertEqual(page.width_input.value(), self.settings.snapshot.width)
        self.assertEqual(page.height_input.value(), self.settings.snapshot.height)
        self.assertFalse(self.window.is_dirty)

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
        self.assertTrue(self.window.apply_changes())
        saved = self.settings.saved[0]
        self.assertEqual((saved.width, saved.height), (400, 350))
        self.assertTrue(saved.always_on_top)
        self.assertFalse(self.window.is_dirty)

    def test_cancel_restores_both_pages(self):
        self.window.appearance_page.width_input.setValue(500)
        self.window.general_page.always_on_top_check.setChecked(True)
        self.window.cancel_changes()
        self.assertEqual(self.window.appearance_page.width_input.value(),
                         self.settings.snapshot.width)
        self.assertFalse(self.window.is_dirty)
        self.assertEqual(self.settings.saved, [])

    def test_reverting_size_clears_dirty_state(self):
        control = self.window.appearance_page.width_input
        control.setValue(500)
        control.setValue(self.settings.snapshot.width)
        self.assertFalse(self.window.is_dirty)
        self.assertFalse(self.window.apply_button.isEnabled())

    def test_save_failure_preserves_size_draft(self):
        self.window.appearance_page.width_input.setValue(500)
        with (
            patch.object(self.settings, "save", side_effect=SettingsValidationError("無效尺寸")),
            patch("ui.dashboard.dashboard_window.QMessageBox.warning"),
        ):
            self.assertFalse(self.window.apply_changes())
        self.assertTrue(self.window.is_dirty)
        self.assertEqual(self.window.appearance_page.width_input.value(), 500)

    def test_discarding_close_restores_size(self):
        self.window.appearance_page.width_input.setValue(500)
        event = QCloseEvent()
        with patch("ui.dashboard.dashboard_window.QMessageBox.question",
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
            "ui.dashboard.dashboard_window.QMessageBox.question",
            return_value=QMessageBox.StandardButton.Discard,
        ):
            self.window.closeEvent(event)

        self.assertTrue(event.isAccepted())
        self.assertFalse(self.window.is_dirty)
        self.assertFalse(self.window.general_page.always_on_top_check.isChecked())
        self.assertEqual(self.settings.saved, [])


if __name__ == "__main__":
    unittest.main()
