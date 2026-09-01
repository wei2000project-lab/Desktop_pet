import json
from pathlib import Path


def default_app_preferences_path() -> Path:
    return Path(__file__).resolve().parent.parent / "config" / "app_preferences.json"


class AppPreferenceStore:
    def __init__(self, path: Path | str | None = None):
        self.path = Path(path) if path is not None else default_app_preferences_path()

    def get_preference(self, category_key: str) -> str:
        preferences = self.load_preferences()
        return preferences.get(_normalize_key(category_key), "")

    def set_preference(self, category_key: str, app_name: str) -> None:
        key = _normalize_key(category_key)
        value = app_name.strip()
        if not key or not value:
            return

        preferences = self.load_preferences()
        preferences[key] = value
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("w", encoding="utf-8") as f:
            json.dump({"preferred_apps": preferences}, f, ensure_ascii=False, indent=2)

    def load_preferences(self) -> dict[str, str]:
        if not self.path.exists():
            return {}

        try:
            with self.path.open("r", encoding="utf-8") as f:
                payload = json.load(f)
        except (OSError, TypeError, ValueError, json.JSONDecodeError):
            return {}

        raw_preferences = payload.get("preferred_apps") if isinstance(payload, dict) else None
        if not isinstance(raw_preferences, dict):
            return {}

        preferences = {}
        for key, value in raw_preferences.items():
            normalized_key = _normalize_key(str(key))
            app_name = str(value).strip()
            if normalized_key and app_name:
                preferences[normalized_key] = app_name
        return preferences


def _normalize_key(value: str) -> str:
    return value.strip().casefold()
