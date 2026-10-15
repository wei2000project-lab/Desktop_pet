from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import Mock, patch

from app.settings.connection_test import run_connection_test


class SettingsConnectionServiceTests(unittest.TestCase):
    def test_service_runs_without_qt_or_application(self):
        source = '''
import sys
from unittest.mock import patch
from app.settings.connection_test import run_connection_test
with patch("app.settings.connection_test.AIClient") as client:
    result = run_connection_test("https://example.test/v1", "fake-key", "model", True)
    assert result.success
    client.return_value.test_connection.assert_called_once()
assert not any(name == "PySide6" or name.startswith("PySide6.") for name in sys.modules)
assert not any(name == "ui" or name.startswith("ui.") for name in sys.modules)
'''
        result = subprocess.run([sys.executable, "-B", "-c", source],
                                cwd=Path(__file__).resolve().parents[1],
                                capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_network_errors_are_returned_as_safe_results(self):
        with patch("app.settings.connection_test.AIClient", side_effect=ValueError("fake-private-body")):
            result = run_connection_test("https://example.test/v1", "fake-key", "model", True)
        self.assertFalse(result.success)
        self.assertNotIn("fake-private-body", repr(result))
        self.assertNotIn("fake-key", repr(result))

    def test_worker_adapts_service_result_and_clears_credential(self):
        from app.settings.connection_test import ConnectionCheckResult
        from app.presentation.settings.connection_test_worker import ConnectionTestWorker
        worker = ConnectionTestWorker(42, "https://example.test/v1", "fake-key", "model", True)
        finished = Mock()
        worker.signals.finished.connect(finished)
        with patch("app.presentation.settings.connection_test_worker.run_connection_test",
                   return_value=ConnectionCheckResult(False, "safe failure")) as service:
            worker.run()
        service.assert_called_once_with("https://example.test/v1", "fake-key", "model", True)
        finished.assert_called_once_with(42, False, "safe failure")
        self.assertEqual(worker.api_key, "")
