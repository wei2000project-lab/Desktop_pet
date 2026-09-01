import os
import json
import subprocess
from pathlib import Path
from typing import Iterable, List, Mapping

from app_control.app_index import AppEntry


SHORTCUT_EXTENSIONS = {".lnk", ".url"}
LAUNCHABLE_FILE_EXTENSIONS = {".exe", ".lnk", ".url"}
REGISTRY_UNINSTALL_PATHS = (
    r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall",
    r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall",
)


def default_start_menu_roots() -> List[Path]:
    roots = [Path(r"C:\ProgramData\Microsoft\Windows\Start Menu\Programs")]
    appdata = os.environ.get("APPDATA")
    if appdata:
        roots.append(Path(appdata) / "Microsoft" / "Windows" / "Start Menu" / "Programs")
    return roots


def scan_start_menu_apps(roots: Iterable[Path | str] | None = None) -> List[AppEntry]:
    scan_roots = [Path(root) for root in (roots or default_start_menu_roots())]
    apps = []
    seen_paths = set()

    for root in scan_roots:
        if not root.exists():
            continue

        for item in root.rglob("*"):
            if not item.is_file() or item.suffix.lower() not in SHORTCUT_EXTENSIONS:
                continue

            resolved = str(item)
            if resolved in seen_paths:
                continue

            seen_paths.add(resolved)
            apps.append(AppEntry(name=item.stem, path=resolved))

    return sorted(apps, key=lambda app: app.name.lower())


def scan_installed_registry_apps(records: Iterable[Mapping[str, str]] | None = None) -> List[AppEntry]:
    registry_records = list(records) if records is not None else _read_installed_app_registry_records()
    apps = []
    seen_paths = set()

    for record in registry_records:
        name = str(record.get("DisplayName") or "").strip()
        path = _launchable_path_from_registry_record(record)
        if not name or not path:
            continue

        normalized_path = str(path)
        if normalized_path in seen_paths:
            continue

        seen_paths.add(normalized_path)
        apps.append(AppEntry(name=name, path=normalized_path))

    return sorted(apps, key=lambda app: app.name.lower())


def scan_start_apps(records: Iterable[Mapping[str, str]] | None = None) -> List[AppEntry]:
    start_app_records = list(records) if records is not None else _read_start_app_records()
    apps = []
    seen_app_ids = set()

    for record in start_app_records:
        name = str(record.get("Name") or "").strip()
        app_id = str(record.get("AppID") or "").strip()
        if not name or not app_id:
            continue

        if app_id.casefold() in seen_app_ids:
            continue

        seen_app_ids.add(app_id.casefold())
        apps.append(AppEntry(name=name, path=f"shell:AppsFolder\\{app_id}"))

    return sorted(apps, key=lambda app: app.name.lower())


def scan_available_apps(
    roots: Iterable[Path | str] | None = None,
    registry_records: Iterable[Mapping[str, str]] | None = None,
    start_app_records: Iterable[Mapping[str, str]] | None = None,
) -> List[AppEntry]:
    apps = []
    seen_keys = set()

    for app in [
        *scan_start_menu_apps(roots),
        *scan_installed_registry_apps(registry_records),
        *scan_start_apps(start_app_records),
    ]:
        key = (app.name.casefold(), app.path.casefold())
        if key in seen_keys:
            continue
        seen_keys.add(key)
        apps.append(app)

    return sorted(apps, key=lambda item: item.name.lower())


def _launchable_path_from_registry_record(record: Mapping[str, str]) -> str:
    for key in ("DisplayIcon", "InstallLocation"):
        raw_value = str(record.get(key) or "").strip()
        if not raw_value:
            continue

        candidate = _clean_registry_path(raw_value)
        if not candidate:
            continue

        path = Path(os.path.expandvars(candidate))
        if _is_launchable_file(path):
            return str(path)

        if _is_directory(path):
            exe = _first_executable_in_directory(path)
            if exe:
                return str(exe)

    return ""


def _clean_registry_path(raw_value: str) -> str:
    value = raw_value.strip()
    if not value:
        return ""

    if value.startswith('"'):
        closing_quote = value.find('"', 1)
        if closing_quote > 0:
            return value[1:closing_quote]

    if "," in value:
        value = value.rsplit(",", 1)[0]

    return value.strip().strip('"')


def _first_executable_in_directory(path: Path) -> Path | None:
    try:
        executables = sorted(path.glob("*.exe"), key=lambda item: item.name.lower())
    except OSError:
        return None
    return executables[0] if executables else None


def _is_launchable_file(path: Path) -> bool:
    if path.suffix.lower() not in LAUNCHABLE_FILE_EXTENSIONS:
        return False
    try:
        return path.is_file()
    except OSError:
        return False


def _is_directory(path: Path) -> bool:
    try:
        return path.is_dir()
    except OSError:
        return False


def _read_installed_app_registry_records() -> List[dict[str, str]]:
    try:
        import winreg
    except ImportError:
        return []

    records = []
    roots = (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER)
    for root in roots:
        for subkey_path in REGISTRY_UNINSTALL_PATHS:
            records.extend(_read_registry_uninstall_key(winreg, root, subkey_path))
    return records


def _read_start_app_records() -> List[dict[str, str]]:
    if os.name != "nt":
        return []

    try:
        completed = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-Command",
                "[Console]::OutputEncoding = [System.Text.Encoding]::UTF8; "
                "Get-StartApps | Select-Object Name,AppID | ConvertTo-Json -Depth 2",
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return []

    stdout = completed.stdout or ""
    if completed.returncode != 0 or not stdout.strip():
        return []

    try:
        payload = json.loads(stdout)
    except json.JSONDecodeError:
        return []

    if isinstance(payload, dict):
        payload = [payload]
    if not isinstance(payload, list):
        return []

    records = []
    for item in payload:
        if isinstance(item, dict):
            records.append({key: str(item.get(key) or "") for key in ("Name", "AppID")})
    return records


def _read_registry_uninstall_key(winreg, root, subkey_path: str) -> List[dict[str, str]]:
    records = []
    try:
        key = winreg.OpenKey(root, subkey_path)
    except OSError:
        return records

    with key:
        try:
            subkey_count = winreg.QueryInfoKey(key)[0]
        except OSError:
            return records

        for index in range(subkey_count):
            try:
                app_subkey_name = winreg.EnumKey(key, index)
                app_key = winreg.OpenKey(key, app_subkey_name)
            except OSError:
                continue

            with app_key:
                record = {}
                for value_name in ("DisplayName", "DisplayIcon", "InstallLocation"):
                    try:
                        value, _ = winreg.QueryValueEx(app_key, value_name)
                    except OSError:
                        continue
                    record[value_name] = str(value)

                if record.get("DisplayName"):
                    records.append(record)

    return records
