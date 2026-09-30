import ast
import os
from pathlib import Path
import subprocess
import sys
import textwrap
import unittest


ROOT = Path(__file__).resolve().parents[1]


class SettingsArchitectureTests(unittest.TestCase):
    def run_isolated(self, source):
        result = subprocess.run(
            [sys.executable, "-c", textwrap.dedent(source)], cwd=ROOT,
            env={**os.environ, "QT_QPA_PLATFORM": "offscreen"},
            capture_output=True, text=True, timeout=15,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_constructing_view_does_not_load_configuration_or_application_services(self):
        self.run_isolated('''
            import sys
            from PySide6.QtWidgets import QApplication
            from ui.settings import SettingsWindow
            app = QApplication([])
            view = SettingsWindow()
            changes = []
            view.settings_changed.connect(changes.append)
            view.general_page.always_on_top_check.setChecked(True)
            view.show()
            app.processEvents()
            view.close()
            assert changes == [{"always_on_top": True}], changes
            forbidden = {"app.core.config_manager", "app.settings.service", "app.settings.session",
                         "app.settings.presenter", "app.settings.editing",
                         "app.settings.connection_test_controller", "app.ai.client"}
            assert not forbidden.intersection(sys.modules), forbidden.intersection(sys.modules)
        ''')

    def test_application_settings_work_without_loading_ui_or_qtwidgets(self):
        self.run_isolated('''
            import sys
            from app.settings.model import SettingsSnapshot
            from app.settings.session import SettingsSession
            from app.settings.presenter import SettingsPresenter
            class Backend:
                def load(self): return SettingsSnapshot()
                def save(self, snapshot): return snapshot
            session = SettingsSession(Backend())
            session.update({"width": 450})
            session.apply()
            assert session.snapshot.width == 450 and not session.is_dirty
            assert "PySide6.QtWidgets" not in sys.modules
            assert not any(name == "ui" or name.startswith("ui.") for name in sys.modules)
        ''')

    def test_view_imports_only_application_data_contracts(self):
        allowed = {"app.settings.model", "app.settings.api_groups", "app.settings.view_contracts"}
        for path in (ROOT / "ui/settings").rglob("*.py"):
            for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
                if isinstance(node, ast.ImportFrom) and node.module and node.module.startswith("app."):
                    self.assertIn(node.module, allowed, str(path))
                elif isinstance(node, ast.Import):
                    for alias in node.names:
                        self.assertFalse(alias.name == "app" or alias.name.startswith("app."), str(path))


if __name__ == "__main__":
    unittest.main()
