import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app_control.app_index import AppEntry, AppIndex
from app_control.app_launcher import AppLauncher
from app_control.app_scanner import (
    _read_start_app_records,
    scan_available_apps,
    scan_installed_registry_apps,
    scan_start_apps,
    scan_start_menu_apps,
)
from app_control.app_open_service import AppOpenService, default_app_index_path


class AppControlTests(unittest.TestCase):
    def test_scanner_only_indexes_shortcuts_and_urls(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "Google Chrome.lnk").write_text("", encoding="utf-8")
            (root / "Docs.url").write_text("", encoding="utf-8")
            (root / "notepad.exe").write_text("", encoding="utf-8")
            (root / "Tools").mkdir()
            (root / "Tools" / "Visual Studio Code.lnk").write_text("", encoding="utf-8")

            apps = scan_start_menu_apps([root])

        self.assertEqual([app.name for app in apps], ["Docs", "Google Chrome", "Visual Studio Code"])
        self.assertTrue(all(app.path.endswith((".lnk", ".url")) for app in apps))

    def test_registry_scanner_indexes_installed_apps_with_display_icon_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            app_path = Path(tmp) / "No Desktop Shortcut.exe"
            app_path.write_text("", encoding="utf-8")

            apps = scan_installed_registry_apps(
                records=[
                    {
                        "DisplayName": "No Desktop Shortcut",
                        "DisplayIcon": f'"{app_path}",0',
                    },
                    {
                        "DisplayName": "No Launch Target",
                    },
                ]
            )

        self.assertEqual(apps, [AppEntry(name="No Desktop Shortcut", path=str(app_path))])

    def test_available_scanner_combines_start_menu_and_registry_apps(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "start"
            root.mkdir()
            (root / "Chrome.lnk").write_text("", encoding="utf-8")
            registry_app = Path(tmp) / "Registry Only.exe"
            registry_app.write_text("", encoding="utf-8")

            apps = scan_available_apps(
                roots=[root],
                registry_records=[
                    {
                        "DisplayName": "Registry Only",
                        "DisplayIcon": str(registry_app),
                    }
                ],
            )

        self.assertEqual([app.name for app in apps], ["Chrome", "Registry Only"])

    def test_start_apps_scanner_indexes_store_apps_like_teams(self):
        apps = scan_start_apps(
            records=[
                {
                    "Name": "Microsoft Teams",
                    "AppID": "MSTeams_8wekyb3d8bbwe!MSTeams",
                }
            ]
        )

        self.assertEqual(
            apps,
            [
                AppEntry(
                    name="Microsoft Teams",
                    path=r"shell:AppsFolder\MSTeams_8wekyb3d8bbwe!MSTeams",
                )
            ],
        )

    def test_start_apps_reader_handles_missing_stdout_after_decode_failure(self):
        class Completed:
            returncode = 0
            stdout = None

        with patch("app_control.app_scanner.subprocess.run", return_value=Completed()):
            records = _read_start_app_records()

        self.assertEqual(records, [])

    def test_available_scanner_combines_start_apps(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "start"
            root.mkdir()
            (root / "Chrome.lnk").write_text("", encoding="utf-8")

            apps = scan_available_apps(
                roots=[root],
                registry_records=[],
                start_app_records=[
                    {
                        "Name": "Microsoft Teams",
                        "AppID": "MSTeams_8wekyb3d8bbwe!MSTeams",
                    }
                ],
            )

        self.assertEqual([app.name for app in apps], ["Chrome", "Microsoft Teams"])

    def test_app_index_saves_loads_and_finds_case_insensitively(self):
        with tempfile.TemporaryDirectory() as tmp:
            index_path = Path(tmp) / "apps.json"
            index = AppIndex(index_path)
            index.save([AppEntry(name="Google Chrome", path="C:/Apps/Chrome.lnk")])

            loaded_index = AppIndex(index_path)
            loaded = loaded_index.load()

        self.assertEqual(loaded[0].name, "Google Chrome")
        self.assertEqual(loaded_index.find_by_name("google chrome").path, "C:/Apps/Chrome.lnk")
        self.assertIsNone(loaded_index.find_by_name("Firefox"))

    def test_launcher_uses_index_path_and_never_accepts_direct_path(self):
        opened = []
        with tempfile.TemporaryDirectory() as tmp:
            shortcut = Path(tmp) / "Chrome.lnk"
            shortcut.write_text("", encoding="utf-8")
            index_path = Path(tmp) / "apps.json"
            AppIndex(index_path).save([AppEntry(name="Google Chrome", path=str(shortcut))])

            launcher = AppLauncher(AppIndex(index_path), opener=opened.append)
            result = launcher.open_app("Google Chrome")
            missing = launcher.open_app(str(shortcut))

        self.assertTrue(result.success)
        self.assertEqual(opened, [str(shortcut)])
        self.assertFalse(missing.success)
        self.assertEqual(missing.error, "app_not_found")

    def test_launcher_accepts_shell_apps_folder_targets_from_start_apps(self):
        opened = []
        with tempfile.TemporaryDirectory() as tmp:
            index_path = Path(tmp) / "apps.json"
            AppIndex(index_path).save(
                [
                    AppEntry(
                        name="Microsoft Teams",
                        path=r"shell:AppsFolder\MSTeams_8wekyb3d8bbwe!MSTeams",
                    )
                ]
            )

            launcher = AppLauncher(AppIndex(index_path), opener=opened.append)
            result = launcher.open_app("Microsoft Teams")

        self.assertTrue(result.success)
        self.assertEqual(opened, [r"shell:AppsFolder\MSTeams_8wekyb3d8bbwe!MSTeams"])

    def test_service_refreshes_index_from_scanner(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "start"
            root.mkdir()
            (root / "Word.lnk").write_text("", encoding="utf-8")
            index_path = Path(tmp) / "apps.json"

            service = AppOpenService(
                index_path=index_path,
                scan_roots=[root],
                opener=lambda path: None,
                registry_records=[],
                start_app_records=[],
            )
            apps = service.refresh_index()

            saved = json.loads(index_path.read_text(encoding="utf-8"))

        self.assertEqual([app.name for app in apps], ["Word"])
        self.assertEqual(saved[0]["name"], "Word")

    def test_service_refreshes_legacy_index_without_start_apps_targets(self):
        with tempfile.TemporaryDirectory() as tmp:
            index_path = Path(tmp) / "apps.json"
            AppIndex(index_path).save([AppEntry(name="Chrome", path="C:/Chrome.lnk")])

            service = AppOpenService(
                index_path=index_path,
                scan_roots=[],
                opener=lambda path: None,
                registry_records=[],
                start_app_records=[
                    {
                        "Name": "Microsoft Teams",
                        "AppID": "MSTeams_8wekyb3d8bbwe!MSTeams",
                    }
                ],
            )

            apps = service.list_apps()

        self.assertIn("Microsoft Teams", [app.name for app in apps])

    def test_default_app_index_path_lives_in_config_directory(self):
        self.assertEqual(default_app_index_path().name, "apps.json")
        self.assertEqual(default_app_index_path().parent.name, "config")

    def test_service_delegates_natural_language_selection_to_selector(self):
        class FakeSelector:
            def __init__(self):
                self.received_text = ""
                self.received_apps = []

            def select_app(self, user_text, apps):
                self.received_text = user_text
                self.received_apps = list(apps)
                return "selection"

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "start"
            root.mkdir()
            (root / "Chrome.lnk").write_text("", encoding="utf-8")
            service = AppOpenService(
                index_path=Path(tmp) / "apps.json",
                scan_roots=[root],
                opener=lambda path: None,
                registry_records=[],
                start_app_records=[],
            )
            selector = FakeSelector()

            selection = service.select_app_from_text("我要上網", selector)

        self.assertEqual(selection, "selection")
        self.assertEqual(selector.received_text, "我要上網")
        self.assertEqual([app.name for app in selector.received_apps], ["Chrome"])


if __name__ == "__main__":
    unittest.main()
