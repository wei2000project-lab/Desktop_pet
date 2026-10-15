import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPoint, Qt, QTimer
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QPushButton

from ui.settings.dialogs import SettingsDialog


class SettingsDialogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_confirm_returns_selected_compatible_button(self):
        dialog = SettingsDialog(
            None,
            "確認刪除",
            "確定要刪除嗎？",
            SettingsDialog.Yes | SettingsDialog.No,
            SettingsDialog.No,
        )
        self.assertEqual(dialog.button(SettingsDialog.Yes).text(), "確認")
        self.assertEqual(dialog.button(SettingsDialog.No).text(), "取消")
        QTimer.singleShot(0, dialog.button(SettingsDialog.Yes).click)
        self.assertEqual(dialog.exec(), int(SettingsDialog.Yes))

    def test_close_uses_safe_fallback(self):
        dialog = SettingsDialog(
            None,
            "尚有未儲存的變更",
            "要在關閉前儲存變更嗎？",
            SettingsDialog.Save | SettingsDialog.Discard | SettingsDialog.Cancel,
            SettingsDialog.Save,
        )
        dialog.reject()
        self.assertEqual(dialog.result(), int(SettingsDialog.Cancel))

    def test_buttons_return_to_normal_after_hover_press_and_focus(self):
        for kind, name in (
            ("question", "settingsDialogPrimary"),
            ("question", "settingsDialogSecondary"),
            ("warning", "settingsDialogDanger"),
            ("question", "settingsDialogClose"),
        ):
            with self.subTest(button=name):
                dialog = SettingsDialog(
                    None, "test", "test", SettingsDialog.Yes | SettingsDialog.No,
                    SettingsDialog.No, kind,
                )
                dialog.show()
                self.app.processEvents()
                button = dialog.findChild(QPushButton, name)

                def background():
                    self.app.processEvents()
                    return button.grab().toImage().pixelColor(10, button.height() // 2).name()

                normal = background()
                QTest.mouseMove(button, QPoint(10, button.height() // 2))
                hover = background()
                QTest.mousePress(button, Qt.LeftButton, pos=QPoint(10, button.height() // 2))
                pressed = background()
                QTest.mouseRelease(button, Qt.LeftButton, pos=QPoint(-10, -10))
                QTest.mouseMove(dialog, QPoint(dialog.width() - 2, dialog.height() - 2))

                self.assertNotEqual(hover, normal)
                self.assertNotEqual(pressed, hover)
                self.assertTrue(button.hasFocus())
                self.assertEqual(background(), normal)
                dialog.close()


if __name__ == "__main__":
    unittest.main()
