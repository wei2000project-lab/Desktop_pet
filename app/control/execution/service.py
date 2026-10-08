import threading
from pathlib import Path
from typing import Callable, Iterable, List, Mapping, Optional

from app.control.discovery.index import AppEntry, AppIndex
from app.control.execution.launcher import AppLaunchResult, AppLauncher
from app.control.resolution.selector import AppSelection
from app.control.resolution.resolver import resolve_preference_change_from_text
from app.control.preferences import AppPreferenceStore, default_app_preferences_path
from app.control.discovery.scanner import default_start_menu_roots, scan_available_apps
from app.core.paths import PROJECT_PATHS
from app.utils.logger import logger


def default_app_index_path() -> Path:
    return PROJECT_PATHS.apps_json


class AppOpenService:
    def __init__(
        self,
        index_path: Path | str,
        scan_roots: Optional[Iterable[Path | str]] = None,
        opener: Optional[Callable[[str], None]] = None,
        preference_store: Optional[AppPreferenceStore] = None,
        registry_records: Optional[Iterable[Mapping[str, str]]] = None,
        start_app_records: Optional[Iterable[Mapping[str, str]]] = None,
    ):
        self.index = AppIndex(index_path)
        self.scan_roots = list(scan_roots) if scan_roots is not None else default_start_menu_roots()
        self.launcher = AppLauncher(self.index, opener=opener)
        self.preference_store = preference_store or AppPreferenceStore(default_app_preferences_path())
        self.registry_records = registry_records
        self.start_app_records = start_app_records
        self._refresh_lock = threading.Lock()
        self._background_lock = threading.Lock()
        self._refresh_thread: threading.Thread | None = None

    def refresh_index(self) -> List[AppEntry]:
        with self._refresh_lock:
            try:
                cached_apps = self.index.list_apps()
            except (OSError, TypeError, ValueError):
                cached_apps = []

            apps = scan_available_apps(
                self.scan_roots,
                registry_records=self.registry_records,
                start_app_records=self.start_app_records,
            )
            if not apps and cached_apps:
                logger.warning("App scan returned no results; keeping the existing app index.")
                return cached_apps
            return self.index.save(apps)

    def refresh_index_in_background(self) -> bool:
        with self._background_lock:
            if self._refresh_thread and self._refresh_thread.is_alive():
                logger.info("App index refresh is already running; skipping duplicate request.")
                return False

            self._refresh_thread = threading.Thread(
                target=self._run_background_refresh,
                daemon=True,
                name="AppIndexRefreshThread",
            )
            self._refresh_thread.start()
            return True

    def _run_background_refresh(self) -> None:
        try:
            apps = self.refresh_index()
            logger.info(f"App index refreshed in background: {len(apps)} apps available.")
        except Exception as exc:
            logger.error(f"Background app index refresh failed; keeping the existing index: {exc}", exc_info=True)

    def list_apps(self) -> List[AppEntry]:
        apps = self.index.list_apps()
        if apps and _has_start_apps_targets(apps):
            return apps
        return self.refresh_index()

    def open_app_by_name(self, app_name: str) -> AppLaunchResult:
        self.list_apps()
        return self.launcher.open_app(app_name)

    def select_app_from_text(self, user_text: str, selector):
        return selector.select_app(user_text, self.list_apps())

    def select_preference_change_from_text(self, user_text: str) -> AppSelection:
        result = resolve_preference_change_from_text(user_text, self.list_apps())
        return AppSelection(
            action="none",
            app_name="",
            confidence=0.0,
            reason=result.reason,
            error=result.error,
            preference_key=result.preference_key,
            choices=result.choices,
        )

    def remember_preferred_app(self, preference_key: str, app_name: str) -> None:
        self.preference_store.set_preference(preference_key, app_name)


def _has_start_apps_targets(apps: Iterable[AppEntry]) -> bool:
    return any(app.path.casefold().startswith("shell:appsfolder\\") for app in apps)
