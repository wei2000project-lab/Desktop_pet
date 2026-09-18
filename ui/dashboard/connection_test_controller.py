"""Own background checks independently of individual key-row widgets."""
from dataclasses import replace
from PySide6.QtCore import QObject, QThreadPool, Slot

from app.settings import SettingsService, SettingsValidationError
from app.settings.connection_test import ConnectionTestWorker
from app.settings.api_groups import APIGroupSettings
from app.settings.api_group_resolver import APIGroupResolutionError, resolve_api_request


class ConnectionTestController(QObject):
    def __init__(self, window, pool=None, worker_factory=ConnectionTestWorker):
        super().__init__(window)
        self.window = window
        self.pool = QThreadPool.globalInstance() if pool is None else pool
        self.worker_factory = worker_factory
        self._session = 0
        self._next_id = 0
        self._jobs = {}
        self._group_jobs = {}

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
        target = self._group_jobs.pop(request_id, None)
        if target is not None:
            group_id, key_id, generation = target
            editor = self.window.ai_page.group_editor
            if job[2] != self._session or generation != editor.generation:
                return
            if editor.test_row(group_id, key_id) is None:
                return
            try:
                current = self._group_snapshot(group_id, key_id)
            except (APIGroupResolutionError, ValueError):
                current = None
            editor.set_test_status(group_id, key_id,
                                   message if current == job[3] else "設定已變更，請重新測試。")
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

    def _group_snapshot(self, group_id, key_id):
        editor = self.window.ai_page.group_editor
        group = next((group for group in editor.collect_settings().groups if group.id == group_id), None)
        if group is None:
            raise ValueError("群組已刪除。")
        if key_id:
            key = next((key for key in group.keys if key.id == key_id), None)
            if key is None:
                raise ValueError("請先輸入 API Key。")
            if group.auth_mode != "api_key":
                raise ValueError("此群組目前使用免金鑰模式。")
            group = replace(group, keys=(replace(key, enabled=True),))
        elif group.auth_mode != "none":
            raise ValueError("請指定要測試的 Key。")
        else:
            group = replace(group, keys=())
        return resolve_api_request(APIGroupSettings((group,), group.id))

    @Slot(str, str)
    def start_group(self, group_id, key_id):
        editor = self.window.ai_page.group_editor
        row = editor.test_row(group_id, key_id)
        if row is None or not row["test_button"].isEnabled():
            return
        editor.commit_pending_input()
        try:
            snapshot = self._group_snapshot(group_id, key_id)
        except (APIGroupResolutionError, ValueError) as error:
            editor.set_test_status(group_id, key_id, str(error))
            return
        if len(self._jobs) >= 4:
            editor.set_test_status(group_id, key_id, "已有多個測試進行中，請稍後再試。")
            return
        self._next_id += 1
        request_id = self._next_id
        worker = self.worker_factory(request_id, snapshot.base_url, snapshot.api_key,
                                     snapshot.model, snapshot.verify_ssl)
        self._jobs[request_id] = (worker, None, self._session, snapshot)
        self._group_jobs[request_id] = (group_id, key_id, editor.generation)
        worker.signals.finished.connect(self._finished)
        editor.set_test_status(group_id, key_id, "測試中…", True)
        try:
            self.pool.start(worker)
        except Exception:
            self._jobs.pop(request_id, None)
            self._group_jobs.pop(request_id, None)
            editor.set_test_status(group_id, key_id, "無法啟動連線測試，請稍後再試。")
