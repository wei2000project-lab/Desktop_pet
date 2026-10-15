"""Run bounded connection checks using plain input data, without widget access."""
from dataclasses import replace

from PySide6.QtCore import QObject, QThreadPool, Signal, Slot

from app.settings.api_groups import APIGroupSettings
from app.settings.api_group_resolver import APIGroupResolutionError, resolve_api_request
from app.settings.connection_test import ConnectionTestWorker
from app.settings.model import SettingsValidationError
from app.settings.service import SettingsService
from app.settings.view_contracts import TestTarget


class ConnectionTestController(QObject):
    started = Signal(object)
    finished = Signal(object, str)

    def __init__(self, session, inputs, parent=None, pool=None, worker_factory=ConnectionTestWorker):
        super().__init__(parent)
        self.session = session
        self.inputs = inputs
        self.pool = QThreadPool.globalInstance() if pool is None else pool
        self.worker_factory = worker_factory
        self._session = 0
        self._next_id = 0
        self._jobs = {}

    def invalidate(self):
        # Keep outstanding jobs counted, but ignore their results after closing/reloading.
        self._session += 1

    def _legacy_fingerprint(self, row_id):
        key = self.inputs().legacy_keys.get(row_id)
        if key is None:
            return None
        snapshot = self.session.snapshot
        return (snapshot.base_url.strip(), key.strip(), snapshot.model.strip(), snapshot.verify_ssl)

    @Slot(int)
    def start(self, row_id):
        target = TestTarget("legacy", row_id=row_id)
        fingerprint = self._legacy_fingerprint(row_id)
        if fingerprint is None:
            return
        if not fingerprint[1]:
            self.finished.emit(target, "請先輸入 API Key。")
            return
        try:
            SettingsService().validate(self.session.snapshot)
        except SettingsValidationError as error:
            self.finished.emit(target, str(error))
            return
        self._start(target, fingerprint, fingerprint)

    def _group_snapshot(self, group_id, key_id):
        group = next((group for group in self.session.groups.groups if group.id == group_id), None)
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
        return resolve_api_request(APIGroupSettings((group,), group.id, self.session.groups.schema_version))

    @Slot(str, str)
    def start_group(self, group_id, key_id):
        inputs = self.inputs()
        if (group_id, key_id) not in inputs.group_targets:
            return
        target = TestTarget("group", group_id=group_id, key_id=key_id,
                            generation=inputs.group_generation)
        try:
            snapshot = self._group_snapshot(group_id, key_id)
        except (APIGroupResolutionError, ValueError) as error:
            self.finished.emit(target, str(error))
            return
        self._start(target, snapshot,
                    (snapshot.base_url, snapshot.api_key, snapshot.model, snapshot.verify_ssl))

    def _start(self, target, fingerprint, arguments):
        if any(job[1] == target and job[2] == self._session for job in self._jobs.values()):
            return
        if len(self._jobs) >= 4:
            self.finished.emit(target, "已有多個測試進行中，請稍後再試。")
            return
        self._next_id += 1
        request_id = self._next_id
        try:
            worker = self.worker_factory(request_id, *arguments)
            self._jobs[request_id] = (worker, target, self._session, fingerprint)
            worker.signals.finished.connect(self._finished)
            self.started.emit(target)
            self.pool.start(worker)
        except Exception:
            self._jobs.pop(request_id, None)
            self.finished.emit(target, "無法啟動連線測試，請稍後再試。")

    @Slot(int, bool, str)
    def _finished(self, request_id, success, message):
        job = self._jobs.pop(request_id, None)
        if job is None or job[2] != self._session:
            return
        _worker, target, _epoch, fingerprint = job
        if target.kind == "legacy":
            current = self._legacy_fingerprint(target.row_id)
            if current is None:
                return
        else:
            inputs = self.inputs()
            if (target.generation != inputs.group_generation
                    or (target.group_id, target.key_id) not in inputs.group_targets):
                return
            try:
                current = self._group_snapshot(target.group_id, target.key_id)
            except (APIGroupResolutionError, ValueError):
                current = None
        self.finished.emit(target, message if current == fingerprint else "設定已變更，請重新測試。")
