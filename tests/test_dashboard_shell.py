import os
import pathlib
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QScrollArea

from ui.dashboard import DashboardWindow
from ui.dashboard.page_registry import default_page_definitions
from ui.dashboard.sidebar import DashboardSidebar


class DashboardShellTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.window = DashboardWindow()

    def tearDown(self):
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
        self.assertEqual(self.window.size().height(), 850)
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

    def test_shell_does_not_read_or_write_settings(self):
        source = "\n".join(
            path.read_text(encoding="utf-8")
            for path in pathlib.Path("ui/dashboard").rglob("*.py")
        )

        self.assertNotIn("settings_service", source)
        self.assertNotIn("config_manager", source)


if __name__ == "__main__":
    unittest.main()
