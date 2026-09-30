import os
from pathlib import Path
import subprocess
import sys
import textwrap
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QLabel, QStyle, QWidget

from ui.dashboard import DashboardWindow
from ui.dashboard.page_registry import PageDefinition
from ui.dashboard.sidebar import DashboardSidebar


class DashboardShellTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.pages = (
            PageDefinition("overview", "總覽", QStyle.SP_DesktopIcon, QWidget),
            PageDefinition("activity", "活動", QStyle.SP_FileDialogInfoView, QWidget),
        )
        self.window = DashboardWindow(page_definitions=self.pages, title="Nova 測試")

    def tearDown(self):
        self.window.close()
        self.window.deleteLater()
        self.app.processEvents()

    def test_window_uses_expected_default_and_minimum_size(self):
        self.assertEqual((self.window.width(), self.window.height()), (900, 650))
        self.assertEqual((self.window.minimumWidth(), self.window.minimumHeight()), (650, 600))
        self.assertEqual(self.window.windowTitle(), "Nova 測試")
        self.assertEqual(self.window.sidebar.title_label.text(), "Nova 測試")

    def test_navigation_selects_matching_page_and_button(self):
        self.assertEqual(self.window.current_page_key, "overview")
        button = self.window.sidebar.button_for_key("activity")
        button.click()
        self.assertEqual(self.window.current_page_key, "activity")
        self.assertIs(self.window.content_stack.currentWidget(), self.window.page_for_key("activity"))
        self.assertTrue(button.isChecked())
        self.assertFalse(self.window.sidebar.button_for_key("overview").isChecked())

    def test_sidebar_collapsed_state_keeps_tooltips_and_selection(self):
        self.window.select_page("activity")
        self.window.sidebar.set_collapsed(True)
        button = self.window.sidebar.button_for_key("activity")
        self.assertTrue(self.window.sidebar.is_collapsed)
        self.assertEqual(self.window.sidebar.width(), DashboardSidebar.COLLAPSED_WIDTH)
        self.assertEqual(button.text(), "")
        self.assertEqual(button.toolTip(), "活動")
        self.assertTrue(button.isChecked())
        self.window.sidebar.set_collapsed(False)
        self.assertEqual(self.window.sidebar.width(), DashboardSidebar.EXPANDED_WIDTH)
        self.assertEqual(button.text(), "活動")

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

    def test_unknown_page_is_rejected_without_changing_selection(self):
        for operation in (self.window.select_page, self.window.page_for_key):
            with self.assertRaises(KeyError):
                operation("missing")
        self.assertEqual(self.window.current_page_key, "overview")

    def test_duplicate_page_keys_are_rejected_before_constructing_pages(self):
        with self.assertRaisesRegex(ValueError, "unique"):
            DashboardWindow(page_definitions=(self.pages[0], self.pages[0]))

    def test_empty_shell_does_not_create_feature_pages(self):
        window = DashboardWindow()
        self.addCleanup(window.deleteLater)
        self.assertIsNone(window.current_page_key)
        self.assertEqual(window.content_stack.count(), 0)

    def test_caller_can_add_footer_without_affecting_navigation(self):
        footer = QLabel("測試狀態")
        self.window.add_content_footer(footer)
        self.window.show()
        self.app.processEvents()
        self.assertTrue(footer.isVisible())
        self.assertGreaterEqual(footer.y(), self.window.content_stack.geometry().bottom())
        self.window.select_page("activity")
        self.assertEqual(self.window.content_stack.count(), 2)
        self.assertTrue(footer.isVisible())

    def test_shell_operates_without_loading_settings_or_application_services(self):
        # A fresh process catches indirect imports hidden by the test runner's cache.
        result = subprocess.run(
            [sys.executable, "-c", textwrap.dedent('''
                import sys
                from PySide6.QtWidgets import QApplication, QStyle, QWidget
                from ui.dashboard import DashboardWindow
                from ui.dashboard.page_registry import PageDefinition

                app = QApplication([])
                window = DashboardWindow(page_definitions=(
                    PageDefinition("sample", "Sample", QStyle.SP_DesktopIcon, QWidget),
                ))
                window.show()
                app.processEvents()
                window.select_page("sample")
                window.close()
                forbidden = [name for name in sys.modules if
                             name == "app" or name.startswith("app.") or
                             name == "ui.settings" or name.startswith("ui.settings.")]
                assert not forbidden, forbidden
            ''')],
            cwd=Path(__file__).resolve().parents[1],
            capture_output=True,
            text=True,
            timeout=15,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
