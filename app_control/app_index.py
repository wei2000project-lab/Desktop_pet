import json
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

    def save(self, apps: Iterable[AppEntry]) -> List[AppEntry]:
        self._apps = sorted(list(apps), key=lambda app: app.name.lower())
        self.index_path.parent.mkdir(parents=True, exist_ok=True)
        with self.index_path.open("w", encoding="utf-8") as f:
            json.dump([asdict(app) for app in self._apps], f, ensure_ascii=False, indent=2)
        return self._apps

    def load(self) -> List[AppEntry]:
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
        return self._apps

    def list_apps(self) -> List[AppEntry]:
        if not self._apps:
            return self.load()
        return self._apps

    def find_by_name(self, app_name: str) -> Optional[AppEntry]:
        needle = app_name.strip().casefold()
        if not needle:
            return None

        for app in self.list_apps():
            if app.name.casefold() == needle:
                return app
        return None
