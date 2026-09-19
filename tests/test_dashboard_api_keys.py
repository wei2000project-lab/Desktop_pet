import os
import unittest
import threading
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtGui import QCloseEvent
from PySide6.QtCore import QThreadPool, QEvent, QCoreApplication
from PySide6.QtWidgets import QApplication, QLineEdit, QMessageBox

from app.settings import ApiKeyEntry
from app.settings.connection_test import ConnectionTestWorker, ConnectionTestSignals
from tests.test_dashboard_shell import FakeSettingsBackend
from ui.dashboard import DashboardWindow


class FakePool:
    def __init__(self):
        self.workers = []

    def start(self, worker):
        self.workers.append(worker)


class FakeWorker:
    def __init__(self, request_id, base_url, api_key, model, verify_ssl):
        self.request_id = request_id
        self.inputs = (base_url, api_key, model, verify_ssl)
        self.signals = ConnectionTestSignals()

    def finish(self, success=True, message="連線測試成功。"):
        self.signals.finished.emit(self.request_id, success, message)


class DashboardApiKeyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.backend = FakeSettingsBackend()
        self.window = DashboardWindow(settings_backend=self.backend)
        self.page = self.window.ai_page
        self.pool = FakePool()
        self.window.connection_tests.pool = self.pool
        self.window.connection_tests.worker_factory = FakeWorker

    def tearDown(self):
        self.window._allow_close = True
        self.window.close()
        self.window.deleteLater()
        self.app.processEvents()

    def key_row(self):
        row = self.page.api_key_rows[0]
        row["key_input"].setText("fake-test-key")
        return row

    def test_add_name_delete_and_apply(self):
        row = self.key_row()
        self.assertEqual(row["key_input"].echoMode(), QLineEdit.Password)
        row["name_input"].setText(" 第一把 ")
        extra = self.page.add_api_key_row("第二把", "fake-second-key")
        self.page.remove_api_key_row(row["id"])
        self.assertTrue(self.window.is_dirty)
        self.assertEqual(self.backend.saved, [])
        self.window.apply_changes()
        self.assertEqual(self.backend.saved[0].api_keys,
                         (ApiKeyEntry("第二把", "fake-second-key"),))
        self.assertEqual(len(self.page.api_key_rows), 1)
        self.assertIsNone(self.page.row_for_id(extra["id"]))

    def test_empty_rows_do_not_dirty_and_cancel_restores_keys(self):
        self.page.add_api_key_row()
        self.assertFalse(self.window.is_dirty)
        self.key_row()
        self.window.cancel_changes()
        self.assertEqual(self.page.collect_api_key_entries(), ())
        self.assertEqual(len(self.page.api_key_rows), 1)
        self.assertFalse(self.window.is_dirty)

    def test_last_row_delete_keeps_one_empty_row(self):
        row = self.key_row()
        self.page.remove_api_key_row(row["id"])
        self.assertEqual(len(self.page.api_key_rows), 1)
        self.assertEqual(self.page.collect_api_key_entries(), ())
        self.assertFalse(self.window.is_dirty)

    def test_test_uses_draft_without_saving_and_blocks_duplicate(self):
        row = self.key_row()
        self.page.base_url_input.setText("https://example.test/v1")
        self.page.model_input.setText("draft-model")
        row["test_button"].click()
        row["test_button"].click()
        self.assertEqual(len(self.pool.workers), 1)
        self.assertEqual(self.pool.workers[0].inputs,
                         ("https://example.test/v1", "fake-test-key", "draft-model", True))
        self.assertFalse(row["test_button"].isEnabled())
        self.window.select_page("general")
        self.assertEqual(self.window.current_page_key, "general")
        self.assertEqual(self.backend.saved, [])
        self.pool.workers[0].finish()
        self.assertTrue(row["test_button"].isEnabled())
        self.assertEqual(row["status"].text(), "連線測試成功。")

    def test_empty_key_and_invalid_model_do_not_start(self):
        row = self.page.api_key_rows[0]
        row["test_button"].click()
        self.assertIn("請先輸入", row["status"].text())
        row["key_input"].setText("fake-test-key")
        self.page.model_input.clear()
        row["test_button"].click()
        self.assertEqual(self.pool.workers, [])
        self.assertIn("模型", row["status"].text())

    def test_deleted_row_result_is_ignored(self):
        row = self.key_row()
        row["test_button"].click()
        self.page.remove_api_key_row(row["id"])
        self.pool.workers[0].finish()
        self.assertEqual(self.page.api_key_rows[0]["status"].text(), "")
        self.assertEqual(self.window.connection_tests._jobs, {})

    def test_edit_during_test_marks_result_stale(self):
        row = self.key_row()
        row["test_button"].click()
        row["key_input"].setText("new-fake-key")
        self.pool.workers[0].finish()
        self.assertIn("設定已變更", row["status"].text())
        self.assertTrue(row["test_button"].isEnabled())

    def test_apply_during_test_does_not_update_rebuilt_rows(self):
        row = self.key_row()
        row["test_button"].click()
        self.window.apply_changes()
        self.pool.workers[0].finish()
        self.assertEqual(self.page.api_key_rows[0]["status"].text(), "")

    def test_accepted_close_ignores_late_result(self):
        row = self.key_row()
        row["test_button"].click()
        event = QCloseEvent()
        with patch("ui.dashboard.dashboard_window.DashboardDialog.question",
                   return_value=QMessageBox.StandardButton.Discard):
            self.window.closeEvent(event)
        self.assertTrue(event.isAccepted())
        self.pool.workers[0].finish()
        self.assertEqual(self.page.api_key_rows[0]["status"].text(), "")

    def test_cancel_close_keeps_test_result_valid(self):
        row = self.key_row()
        row["test_button"].click()
        event = QCloseEvent()
        with patch("ui.dashboard.dashboard_window.DashboardDialog.question",
                   return_value=QMessageBox.StandardButton.Cancel):
            self.window.closeEvent(event)
        self.assertFalse(event.isAccepted())
        self.pool.workers[0].finish()
        self.assertEqual(row["status"].text(), "連線測試成功。")

    def test_outstanding_tests_are_bounded(self):
        for index in range(5):
            row = self.page.add_api_key_row(str(index), "fake-test-key")
            row["test_button"].click()
        self.assertEqual(len(self.pool.workers), 4)
        self.assertIn("稍後", row["status"].text())

    def test_real_thread_pool_leaves_ui_responsive(self):
        entered = threading.Event()
        release = threading.Event()
        pool = QThreadPool()
        self.window.connection_tests.pool = pool
        self.window.connection_tests.worker_factory = ConnectionTestWorker
        row = self.key_row()

        def connection_check():
            entered.set()
            release.wait(2)

        with patch("app.settings.connection_test.AIClient") as client:
            client.return_value.test_connection.side_effect = connection_check
            try:
                row["test_button"].click()
                self.assertTrue(entered.wait(1))
                self.window.select_page("behavior")
                self.app.processEvents()
                self.assertEqual(self.window.current_page_key, "behavior")
                self.assertFalse(row["test_button"].isEnabled())
            finally:
                release.set()
                self.assertTrue(pool.waitForDone(2000))
            self.app.processEvents()
        self.assertEqual(row["status"].text(), "連線測試成功。")

    def test_destroyed_window_disconnects_worker_result(self):
        row = self.key_row()
        row["test_button"].click()
        worker = self.pool.workers[0]
        self.window._allow_close = True
        self.window.close()
        self.window.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        worker.finish()
        self.app.processEvents()
        # tearDown must not touch a C++ widget already destroyed.
        self.window = DashboardWindow(settings_backend=self.backend)


class ConnectionWorkerTests(unittest.TestCase):
    def test_success_uses_timeout_and_never_saves(self):
        worker = ConnectionTestWorker(1, "https://example.test/v1", "fake-key", "test", True)
        results = []
        worker.signals.finished.connect(lambda *args: results.append(args))
        with patch("app.settings.connection_test.AIClient") as client:
            worker.run()
            client.assert_called_once_with(base_url="https://example.test/v1",
                                           api_key="fake-key", model="test",
                                           verify_ssl=True, timeout=15.0)
            client.return_value.test_connection.assert_called_once()
        self.assertEqual(results, [(1, True, "連線測試成功。")])
        self.assertEqual(worker.api_key, "")

    def test_failure_does_not_expose_key_or_server_body(self):
        for error in ("HTTP 401 fake-key server-secret", "HTTP 429 fake-key",
                      "HTTP 500 fake-key", "連線逾時 fake-key", "unexpected fake-key"):
            with self.subTest(error=error):
                worker = ConnectionTestWorker(1, "https://example.test", "fake-key", "test", True)
                results = []
                worker.signals.finished.connect(lambda *args: results.append(args))
                with patch("app.settings.connection_test.AIClient") as client:
                    client.return_value.test_connection.side_effect = Exception(error)
                    worker.run()
                self.assertFalse(results[0][1])
                self.assertNotIn("fake-key", results[0][2])
                self.assertNotIn("server-secret", results[0][2])
                self.assertEqual(worker.api_key, "")


if __name__ == "__main__":
    unittest.main()
