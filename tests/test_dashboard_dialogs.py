import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from ui.dashboard.dialogs import DashboardDialog


class DashboardDialogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_confirm_returns_selected_compatible_button(self):
        dialog = DashboardDialog(
            None,
            "確認刪除",
            "確定要刪除嗎？",
            DashboardDialog.Yes | DashboardDialog.No,
            DashboardDialog.No,
        )
        self.assertEqual(dialog.button(DashboardDialog.Yes).text(), "確認")
        self.assertEqual(dialog.button(DashboardDialog.No).text(), "取消")
        QTimer.singleShot(0, dialog.button(DashboardDialog.Yes).click)
        self.assertEqual(dialog.exec(), int(DashboardDialog.Yes))

    def test_close_uses_safe_fallback(self):
        dialog = DashboardDialog(
            None,
            "尚有未儲存的變更",
            "要在關閉前儲存變更嗎？",
            DashboardDialog.Save | DashboardDialog.Discard | DashboardDialog.Cancel,
            DashboardDialog.Save,
        )
        dialog.reject()
        self.assertEqual(dialog.result(), int(DashboardDialog.Cancel))


if __name__ == "__main__":
    unittest.main()
