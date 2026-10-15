"""Qt execution adapter; request and error rules live in the service."""
from PySide6.QtCore import QObject, QRunnable, Signal, Slot
from app.settings.connection_test import run_connection_test


class ConnectionTestSignals(QObject):
    finished = Signal(int, bool, str)


class ConnectionTestWorker(QRunnable):
    def __init__(self, request_id, base_url, api_key, model, verify_ssl):
        super().__init__()
        self.request_id = request_id
        self.base_url = base_url
        self.api_key = api_key
        self.model = model
        self.verify_ssl = verify_ssl
        self.signals = ConnectionTestSignals()

    @Slot()
    def run(self):
        try:
            result = run_connection_test(self.base_url, self.api_key, self.model, self.verify_ssl)
            self.signals.finished.emit(self.request_id, result.success, result.message)
        finally:
            self.api_key = ""
