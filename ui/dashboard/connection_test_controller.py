"""Own background checks independently of individual key-row widgets."""
from PySide6.QtCore import QObject, QThreadPool, Slot

from app.settings import SettingsService, SettingsValidationError
from app.settings.connection_test import ConnectionTestWorker


class ConnectionTestController(QObject):
    def __init__(self, window, pool=None, worker_factory=ConnectionTestWorker):
        super().__init__(window)
        self.window = window
        self.pool = QThreadPool.globalInstance() if pool is None else pool
        self.worker_factory = worker_factory
        self._session = 0
        self._next_id = 0
        self._jobs = {}

    def invalidate(self):
        # In-flight network calls may finish, but may no longer update the UI.
        self._session += 1

    def start(self, row_id):
        page = self.window.ai_page
        row = page.row_for_id(row_id)
        if row is None or not row["test_button"].isEnabled():
            return
        snapshot = self.window._draft_snapshot
        key = row["key_input"].text().strip()
        if not key:
            page.finish_test(row_id, "請先輸入 API Key。")
            return
        try:
            SettingsService().validate(snapshot)
        except SettingsValidationError as error:
            page.finish_test(row_id, str(error))
            return
        # Limit outstanding calls, including calls for rows since removed.
        if len(self._jobs) >= 4:
            page.finish_test(row_id, "已有多個測試進行中，請稍後再試。")
            return
        self._next_id += 1
        worker = self.worker_factory(
            self._next_id, snapshot.base_url.strip(), key,
            snapshot.model.strip(), snapshot.verify_ssl,
        )
        fingerprint = page.connection_fingerprint(row_id, snapshot.verify_ssl)
        self._jobs[self._next_id] = (worker, row_id, self._session, fingerprint)
        worker.signals.finished.connect(self._finished)
        page.begin_test(row_id)
        self.pool.start(worker)

    @Slot(int, bool, str)
    def _finished(self, request_id, success, message):
        job = self._jobs.pop(request_id, None)
        if job is None:
            return
        _worker, row_id, session, fingerprint = job
        if session != self._session:
            return
        page = self.window.ai_page
        if page.row_for_id(row_id) is None:
            return
        current = page.connection_fingerprint(row_id, self.window._draft_snapshot.verify_ssl)
        if fingerprint != current:
            page.finish_test(row_id, "設定已變更，請重新測試。")
            return
        page.finish_test(row_id, message)
