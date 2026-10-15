from pathlib import Path
import unittest

from tests.settings_boundaries import boundary_violations, public_view_members


ROOT = Path(__file__).resolve().parents[1]
MEMBERS = public_view_members((ROOT / "app/presentation/settings/view_port.py").read_text(encoding="utf-8"))


class SettingsBoundaryTests(unittest.TestCase):
    def test_current_layers_and_composition_obey_dependency_rules(self):
        directories = ("ui/dashboard", "ui/settings", "app/contracts", "app/settings",
                       "app/presentation/settings", "app/core")
        for directory in directories:
            for path in (ROOT / directory).rglob("*.py"):
                relative = path.relative_to(ROOT).with_suffix("")
                is_package = relative.name == "__init__"
                module = '.'.join((relative.parent if is_package else relative).parts)
                with self.subTest(path=str(relative)):
                    self.assertEqual(boundary_violations(path.read_text(encoding="utf-8"), module,
                                                        MEMBERS, is_package=is_package), [])

    def test_checker_rejects_environment_io_and_aliases(self):
        for source in (
            "import os as env\nvalue = env.getenv('FAKE')",
            "from pathlib import Path as File\nvalue = File('x').read_text()",
            "import requests as network\nnetwork.get('https://example.test')",
            "reader = open\nreader('x')",
            "from PySide6.QtCore import QSettings as Store\nStore()",
            "__import__('os')",
        ):
            with self.subTest(source=source):
                self.assertTrue(boundary_violations(source, "ui.settings.pages.example", MEMBERS))

    def test_checker_rejects_reverse_and_relative_imports(self):
        for module, source in (
            ("app.settings.example", "from ..presentation.settings import presenter"),
            ("app.settings.example", "from ui import settings"),
            ("app.settings.example", "from PySide6 import QtWidgets as widgets"),
            ("app.presentation.settings.example", "from ui.settings import SettingsWindow"),
            ("app.presentation.settings.example", "from app.core.config_manager import config_manager"),
            ("app.contracts.example", "from app.settings.model import SettingsSnapshot"),
        ):
            with self.subTest(module=module, source=source):
                self.assertTrue(boundary_violations(source, module, MEMBERS))

    def test_checker_rejects_widget_access_through_view_alias(self):
        source = "def render(self):\n    window = self.view\n    window.ai_page.model_input.setText('x')"
        self.assertTrue(boundary_violations(source, "app.presentation.settings.presenter", MEMBERS))
        self.assertEqual(boundary_violations(
            "def render(self):\n    self.view.show_dirty_state(True)",
            "app.presentation.settings.presenter", MEMBERS), [])

    def test_local_aliases_do_not_leak_between_functions(self):
        for source, rejected in (
            ("def a():\n reader = open\n reader('x')\ndef b():\n reader = str", True),
            ("def a():\n reader = str\n reader('x')\ndef b():\n reader = open", False),
            ("def a():\n from PySide6.QtCore import QSettings as Store\n Store()\n"
             "def b():\n Store = str", True),
        ):
            with self.subTest(source=source):
                self.assertEqual(bool(boundary_violations(source, "ui.settings.example", MEMBERS)), rejected)
        source = ("def a(self):\n window = self.view\n window.ai_page.setText('x')\n"
                  "def b(self):\n window = other")
        self.assertTrue(boundary_violations(source, "app.presentation.settings.presenter", MEMBERS))

    def test_alias_reassignment_is_evaluated_in_source_order(self):
        for source, rejected in (
            ("reader = open\nreader('x')\nreader = str", True),
            ("reader = open\nreader = str\nreader('x')", False),
            ("reader = str\nreader('x')\nreader = open", False),
        ):
            with self.subTest(source=source):
                self.assertEqual(bool(boundary_violations(source, "ui.settings.example", MEMBERS)), rejected)

    def test_function_parameters_shadow_outer_aliases(self):
        source = "reader = open\ndef render(reader):\n reader('x')"
        self.assertEqual(boundary_violations(source, "ui.settings.example", MEMBERS), [])

    def test_composition_exception_is_limited_to_one_entry_function(self):
        source = "class WindowManager:\n    def show_settings(self):\n        from app.presentation.settings.presenter import SettingsPresenter"
        self.assertEqual(boundary_violations(source, "app.core.window_manager", MEMBERS), [])
        self.assertTrue(boundary_violations(source, "app.core.other_manager", MEMBERS))
        self.assertTrue(boundary_violations(source.replace("show_settings", "save"),
                                            "app.core.window_manager", MEMBERS))
        self.assertTrue(boundary_violations(source.replace("WindowManager", "OtherManager"),
                                            "app.core.window_manager", MEMBERS))
        nested = ("class WindowManager:\n    def show_settings(self):\n        def later():\n"
                  "            from app.presentation.settings.presenter import SettingsPresenter")
        self.assertTrue(boundary_violations(nested, "app.core.window_manager", MEMBERS))
