"""In-memory settings backends and connection workers for UI tests."""

from app.settings import SettingsService, SettingsSnapshot
from app.presentation.settings.connection_test_worker import ConnectionTestSignals


class FakeSettingsBackend:
    def __init__(self):
        self.snapshot = SettingsSnapshot(always_on_top=False)
        self.saved = []
        self.history_clear_count = 0

    def load(self):
        return self.snapshot

    def save(self, snapshot):
        validator = SettingsService()
        snapshot = validator.normalize(snapshot)
        validator.validate(snapshot)
        self.saved.append(snapshot)
        self.snapshot = snapshot
        return snapshot

    def clear_history(self):
        self.history_clear_count += 1


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


def create_settings_window(settings_backend=None, group_backend=None, **view_options):
    from app.presentation.settings.presenter import SettingsPresenter
    from app.settings.session import SettingsSession
    from ui.settings import SettingsWindow

    window = SettingsWindow(**view_options)
    session = SettingsSession(settings_backend, group_backend)
    presenter = SettingsPresenter(window, session)
    return window, presenter
