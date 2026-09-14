import os
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

from app.control.discovery.index import AppIndex


@dataclass(frozen=True)
class AppLaunchResult:
    success: bool
    app_name: str
    path: str = ""
    error: str = ""
    detail: str = ""


class AppLauncher:
    def __init__(self, app_index: AppIndex, opener: Optional[Callable[[str], None]] = None):
        self.app_index = app_index
        self.opener = opener or self._default_opener

    def open_app(self, app_name: str) -> AppLaunchResult:
        app = self.app_index.find_by_name(app_name)
        if not app:
            return AppLaunchResult(success=False, app_name=app_name, error="app_not_found")

        if not _is_shell_apps_folder_target(app.path) and not Path(app.path).exists():
            return AppLaunchResult(
                success=False,
                app_name=app.name,
                path=app.path,
                error="shortcut_not_found",
            )

        try:
            self.opener(app.path)
        except OSError as exc:
            error = "launch_cancelled" if getattr(exc, "winerror", None) == 1223 else "launch_failed"
            return AppLaunchResult(
                success=False,
                app_name=app.name,
                path=app.path,
                error=error,
                detail=str(exc),
            )
        except Exception as exc:
            return AppLaunchResult(
                success=False,
                app_name=app.name,
                path=app.path,
                error="launch_failed",
                detail=str(exc),
            )
        return AppLaunchResult(success=True, app_name=app.name, path=app.path)

    @staticmethod
    def _default_opener(path: str) -> None:
        startfile = getattr(os, "startfile", None)
        if not startfile:
            raise RuntimeError("os.startfile is only available on Windows")
        startfile(path)


def _is_shell_apps_folder_target(path: str) -> bool:
    return path.casefold().startswith("shell:appsfolder\\")
