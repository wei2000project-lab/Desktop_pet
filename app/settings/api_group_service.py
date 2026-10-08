"""Group persistence and explicit legacy migration for formal requests."""
import os
from threading import RLock

api_group_lock = RLock()

from app.core.config_manager import config_manager
from app.core.event_bus import event_bus
from app.settings.api_groups import (
    APIGroupDataError, APIGroupSettings, deserialize_api_groups,
    migrate_legacy_api, serialize_api_groups,
)


class APIGroupService:
    def __init__(self, store=config_manager, publish=event_bus.publish):
        self.store = store
        self.publish = publish

    def load(self) -> APIGroupSettings | None:
        try:
            contents = self.store.get_api_group_contents()
        except (OSError, UnicodeError):
            raise APIGroupDataError("API 群組檔案無法讀取；原資料未修改。") from None
        return None if contents is None else deserialize_api_groups(contents)

    def save(self, settings: APIGroupSettings) -> APIGroupSettings:
        with api_group_lock:
            return self._save(settings)

    def _save(self, settings):
        contents = serialize_api_groups(settings)
        self.load()  # Do not silently overwrite corrupt/unsupported existing files.
        try:
            self.store.save_api_group_contents(contents)
        except (OSError, UnicodeError):
            raise APIGroupDataError("API 群組儲存失敗；請確認權限或稍後再試。") from None
        self.publish("config_updated")
        return settings

    def migrate(self, environment=None) -> APIGroupSettings:
        """Explicit one-time operation; an empty valid file is already migrated."""
        if getattr(self.store, "categorized_data", False) is True:
            raise APIGroupDataError("分類後不再從舊 API 設定建立群組。")
        with api_group_lock:
            return self._migrate(environment)

    def _migrate(self, environment):
        existing = self.load()
        if existing is not None:
            return existing
        environment = os.environ if environment is None else environment
        settings = migrate_legacy_api(
            self.store.get_legacy_api_values(),
            environment_available=bool(environment.get("OPENAI_API_KEY", "").strip()),
        )
        return self.save(settings)

    def resolve_request(self, *, environment=None, temperature_override=None):
        """Read saved groups only; missing data does not trigger migration or writes."""
        from app.settings.api_group_resolver import resolve_api_request

        return resolve_api_request(self.load(), environment=environment,
                                   temperature_override=temperature_override)

    def resolve_runtime_request(self, *, environment=None, temperature_override=None):
        """Migrate only missing files; never resurrect legacy settings after deletion."""
        from app.settings.api_group_resolver import resolve_api_request

        if getattr(self.store, "categorized_data", False) is True:
            return resolve_api_request(self.load(), environment=environment,
                                       temperature_override=temperature_override)
        return resolve_api_request(self.migrate(environment), environment=environment,
                                   temperature_override=temperature_override)
