import json
import os
import tempfile
import threading
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable, List, Optional


@dataclass(frozen=True)
class AppEntry:
    name: str
    path: str


class AppIndex:
    def __init__(self, index_path: Path | str):
        self.index_path = Path(index_path)
        self._apps: List[AppEntry] = []
        self._lock = threading.RLock()

    def save(self, apps: Iterable[AppEntry]) -> List[AppEntry]:
        sorted_apps = sorted(list(apps), key=lambda app: app.name.lower())
        with self._lock:
            self.index_path.parent.mkdir(parents=True, exist_ok=True)
            temp_path = None
            try:
                with tempfile.NamedTemporaryFile(
                    mode="w",
                    encoding="utf-8",
                    dir=self.index_path.parent,
                    prefix=f".{self.index_path.name}.",
                    suffix=".tmp",
                    delete=False,
                ) as f:
                    temp_path = Path(f.name)
                    json.dump([asdict(app) for app in sorted_apps], f, ensure_ascii=False, indent=2)
                    f.flush()
                    os.fsync(f.fileno())
                os.replace(temp_path, self.index_path)
                self._apps = sorted_apps
            finally:
                if temp_path and temp_path.exists():
                    try:
                        temp_path.unlink()
                    except OSError:
                        pass
            return list(self._apps)

    def load(self) -> List[AppEntry]:
        with self._lock:
            if not self.index_path.exists():
                self._apps = []
                return []

            with self.index_path.open("r", encoding="utf-8") as f:
                raw_apps = json.load(f)

            self._apps = [
                AppEntry(name=str(item["name"]), path=str(item["path"]))
                for item in raw_apps
                if isinstance(item, dict) and item.get("name") and item.get("path")
            ]
            return list(self._apps)

    def list_apps(self) -> List[AppEntry]:
        with self._lock:
            if not self._apps:
                return self.load()
            return list(self._apps)

    def find_by_name(self, app_name: str) -> Optional[AppEntry]:
        needle = app_name.strip().casefold()
        if not needle:
            return None

        for app in self.list_apps():
            if app.name.casefold() == needle:
                return app
        return None
