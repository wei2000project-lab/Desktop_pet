import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

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


if __name__ == "__main__":
    unittest.main()
