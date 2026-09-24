import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtGui import QWheelEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from ui.dashboard.input_controls import NoWheelCheckBox, NoWheelComboBox, ToggleSwitch
from ui.dashboard.number_input import DecimalInput, IntegerInput
from ui.dashboard.pages.appearance_page import AppearancePage
from ui.dashboard import DashboardWindow
from tests.test_dashboard_shell import FakeSettingsBackend


class DashboardInputControlTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.window = DashboardWindow(settings_backend=FakeSettingsBackend())
        self.window.select_page("appearance")
        self.page = self.window.appearance_page
        self.page.widget().setMinimumHeight(1200)
        self.window.show()
        self.app.processEvents()

    def tearDown(self):
        self.window._allow_close = True
        self.window.close()
        self.window.deleteLater()
        self.app.processEvents()

    @staticmethod
    def wheel_event():
        return QWheelEvent(
            QPointF(5, 5), QPointF(5, 5), QPoint(), QPoint(0, -120),
            Qt.NoButton, Qt.NoModifier, Qt.ScrollUpdate, False,
        )

    def assert_page_scrolls(self, target):
        bar = self.page.verticalScrollBar()
        bar.setValue(80)
        QApplication.sendEvent(target, self.wheel_event())
        self.assertGreater(bar.value(), 80)

    def test_dashboard_wheel_changes_only_outer_page_for_combo_and_checkbox(self):
        combo = NoWheelComboBox(self.page.widget())
        combo.addItems(["第一個", "第二個"])
        checkbox = NoWheelCheckBox("測試", self.page.widget())
        checkbox.setChecked(True)
        for target in (combo, checkbox):
            with self.subTest(target=type(target).__name__):
                self.assert_page_scrolls(target)
        self.assertEqual(combo.currentIndex(), 0)
        self.assertTrue(checkbox.isChecked())

    def test_dashboard_wheel_changes_only_outer_page_for_integer_and_decimal(self):
        integer = self.page.width_input
        decimal = DecimalInput(self.page.widget())
        decimal.setRange(0, 10)
        decimal.setValue(0.7)
        for control, value in ((integer, integer.value()), (decimal, 0.7)):
            control.editor.clearFocus()
            control.editor.lineEdit().deselect()
            with self.subTest(control=type(control).__name__):
                self.assert_page_scrolls(control.editor.lineEdit())
                self.assertEqual(control.value(), value)
                self.assertFalse(control.editor.hasFocus())
                self.assertEqual(control.editor.lineEdit().selectedText(), "")

    def test_wheel_commits_and_clears_focused_numeric_editor(self):
        control = self.page.width_input
        control.editor.setFocus()
        control.editor.lineEdit().setText("333")
        control.editor.lineEdit().selectAll()
        self.app.processEvents()
        self.assertTrue(control.editor.hasFocus())
        self.assertTrue(control.editor.lineEdit().selectedText())

        self.assert_page_scrolls(control.editor.lineEdit())

        self.assertEqual(control.value(), 333)
        self.assertFalse(control.editor.hasFocus())
        self.assertFalse(control.editor.lineEdit().hasFocus())
        self.assertEqual(control.editor.lineEdit().selectedText(), "")

    def test_step_buttons_and_keyboard_api_still_change_numbers(self):
        control = IntegerInput()
        control.setRange(0, 10)
        control.setValue(4)
        control.plus_button.click()
        self.assertEqual(control.value(), 5)
        control.minus_button.click()
        self.assertEqual(control.value(), 4)
        control.editor.setValue(7)
        self.assertEqual(control.value(), 7)

    def test_step_button_commits_typed_text_before_stepping(self):
        control = IntegerInput()
        control.show()
        control.setRange(0, 10)
        control.setValue(2)
        control.editor.setFocus()
        self.app.processEvents()
        control.editor.lineEdit().setText("6")
        control.plus_button.click()
        self.assertEqual(control.value(), 7)
        self.assertFalse(control.editor.hasFocus())
        self.assertEqual(control.editor.lineEdit().selectedText(), "")
        control.close()

    def test_clicking_page_background_finishes_numeric_input(self):
        page = AppearancePage()
        page.resize(500, 500)
        page.show()
        self.app.processEvents()
        editor = page.width_input.editor
        finished = []
        editor.editingFinished.connect(lambda: finished.append(True))
        editor.setFocus()
        editor.lineEdit().setText("333")
        self.app.processEvents()
        QTest.mouseClick(page.widget(), Qt.LeftButton,
                         pos=QPoint(10, page.widget().height() - 10))
        self.app.processEvents()
        self.assertFalse(editor.hasFocus())
        self.assertEqual(page.width_input.value(), 333)
        self.assertEqual(editor.lineEdit().selectedText(), "")
        self.assertEqual(finished, [True])
        page.close()

    def test_focused_toggle_does_not_draw_an_unrelated_purple_outline(self):
        toggle = ToggleSwitch()
        toggle.show()
        toggle.setFocus()
        self.app.processEvents()

        image = toggle.grab().toImage()

        self.assertNotEqual(image.pixelColor(1, 1).name(), "#5f2d82")
        toggle.close()


if __name__ == "__main__":
    unittest.main()
