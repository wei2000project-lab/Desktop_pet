"""Load, validate, and persist editable application settings."""
import math
import os
from dataclasses import replace
from typing import Callable
from urllib.parse import urlsplit

from app.core.config_manager import config_manager
from app.core.event_bus import event_bus
from app.settings.model import ApiKeyEntry, SettingsSnapshot, SettingsValidationError
from app.settings.editing import normalize_key_entries


LEGACY_PERSONALITY_MAP = {
    "cute": "catgirl_companion",
    "catgirl": "catgirl_companion",
    "gentle": "warm_companion",
    "concise": "concise_assistant",
    "proactive": "energetic_partner",
    "few_emoticons": "catgirl_companion",
}


class SettingsService:
    def __init__(self, store=config_manager, publish: Callable[..., None] = event_bus.publish):
        self.store = store
        self.publish = publish

    def load(self) -> SettingsSnapshot:
        prompt_data = self.store.get_prompt()
        selected_personality = (prompt_data.get("selected_personality") or "").strip()
        if not selected_personality:
            legacy_options = prompt_data.get("personality_options") or []
            if legacy_options:
                selected_personality = LEGACY_PERSONALITY_MAP.get(legacy_options[0], "")

        try:
            temperature = float(self.store.get_api("Temperature", "0.7"))
        except (TypeError, ValueError):
            temperature = 0.7
        if not math.isfinite(temperature) or not 0.0 <= temperature <= 2.0:
            temperature = 0.7

        api_keys = tuple(
            ApiKeyEntry(entry.get("name", ""), entry.get("key", ""))
            for entry in self.store.get_api_key_entries()
        )
        snapshot = SettingsSnapshot(
            api_keys=api_keys,
            base_url=self.store.get_api("BaseUrl", "https://api.openai.com/v1"),
            model=self.store.get_api("Model", "gpt-4o-mini"),
            temperature=temperature,
            verify_ssl=str(self.store.get_api("VerifySSL", "true")).lower() == "true",
            width=self.store.get_general_int("Width", 250),
            height=self.store.get_general_int("Height", 250),
            always_on_top=self.store.get_general_bool("AlwaysOnTop", True),
            max_memory_turns=self.store.get_general_int("MaxMemoryTurns", 6),
            history_limit=self.store.get_general_int("HistoryLimit", 20),
            conversation_summary_enabled=self.store.get_general_bool("ConversationSummaryEnabled", True),
            reading_idle_seconds=self.store.get_general_int("ReadingIdleSeconds", 300),
            selected_personality=selected_personality,
            custom_personality=prompt_data.get("custom_personality") or "",
        )
        return self.normalize(snapshot)

    def normalize(self, snapshot: SettingsSnapshot) -> SettingsSnapshot:
        normalized_keys = normalize_key_entries(snapshot.api_keys)

        base_url = snapshot.base_url.strip()
        model = snapshot.model.strip()
        custom_personality = snapshot.custom_personality.strip()
        selected_personality = snapshot.selected_personality.strip()

        return replace(
            snapshot,
            api_keys=normalized_keys,
            base_url=base_url,
            model=model,
            custom_personality=custom_personality,
            selected_personality=selected_personality,
        )

    def validate(self, snapshot: SettingsSnapshot, *, include_legacy_api=True) -> None:
        if include_legacy_api:
            self._validate_legacy_api(snapshot)

        self._validate_range("桌寬", snapshot.width, 100, 1000)
        self._validate_range("桌高", snapshot.height, 100, 1000)
        self._validate_range("最大記憶輪數", snapshot.max_memory_turns, 0, 50)
        self._validate_range("歷史紀錄上限", snapshot.history_limit, 1, 100)
        self._validate_range("閱讀閒置秒數", snapshot.reading_idle_seconds, 10, 3600)

    def _validate_legacy_api(self, snapshot):
        if not snapshot.base_url:
            raise SettingsValidationError("Base URL 不可留空。")
        parsed_url = urlsplit(snapshot.base_url)
        if parsed_url.scheme not in {"http", "https"} or not parsed_url.netloc:
            raise SettingsValidationError("Base URL 必須是有效的 HTTP 或 HTTPS 網址。")
        if not snapshot.model:
            raise SettingsValidationError("模型名稱不可留空。")
        if not math.isfinite(snapshot.temperature) or not 0.0 <= snapshot.temperature <= 2.0:
            raise SettingsValidationError("Temperature 必須介於 0.0 到 2.0。")

    def save(self, snapshot: SettingsSnapshot, *, api_groups=None, group_settings_mode=False) -> SettingsSnapshot:
        from app.settings.api_group_service import api_group_lock

        with api_group_lock:
            return self._save(snapshot, api_groups=api_groups, group_settings_mode=group_settings_mode)

    def _save(self, snapshot, *, api_groups=None, group_settings_mode=False):
        normalized = self.normalize(snapshot)
        self.validate(normalized, include_legacy_api=not group_settings_mode)
        group_options = {}
        environment_updates = {}
        if group_settings_mode:
            group_options["preserve_legacy_api"] = True
        if api_groups is not None:
            from app.settings.api_group_service import APIGroupService
            from app.settings.api_groups import ENV_SCHEMA_VERSION, serialize_api_groups

            previous = APIGroupService(self.store, self.publish).load()
            if api_groups.schema_version == ENV_SCHEMA_VERSION:
                from app.core.dotenv_file import DotEnvFile
                from app.settings.env_group_storage import prepare_env_groups

                group_options["preserve_legacy_api"] = True
                api_groups, environment_updates, owned = prepare_env_groups(api_groups, previous)
                if environment_updates:
                    group_options["env_contents"] = DotEnvFile(self.store.env_path).render_updates(
                        environment_updates, owned_existing=owned,
                    )
            group_options["api_group_contents"] = serialize_api_groups(api_groups)
        self.store.save_settings_bundle(
            general_values={
                "Width": normalized.width,
                "Height": normalized.height,
                "AlwaysOnTop": str(normalized.always_on_top).lower(),
                "MaxMemoryTurns": normalized.max_memory_turns,
                "ConversationSummaryEnabled": str(normalized.conversation_summary_enabled).lower(),
                "HistoryLimit": normalized.history_limit,
                "ReadingIdleSeconds": normalized.reading_idle_seconds,
            },
            api_values={} if group_settings_mode else {
                "BaseUrl": normalized.base_url,
                "Model": normalized.model,
                "Temperature": f"{normalized.temperature:.1f}",
            },
            api_key_entries=[{"name": entry.name, "key": entry.key} for entry in normalized.api_keys],
            prompt_values={
                "selected_personality": normalized.selected_personality,
                "custom_personality": normalized.custom_personality,
            },
            **group_options,
        )
        for name, value in environment_updates.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value
        self.publish("config_updated")
        return normalized

    def clear_history(self) -> None:
        self.store.clear_history()
        self.publish("history_cleared")

    @staticmethod
    def _validate_range(label: str, value: int, minimum: int, maximum: int) -> None:
        if not minimum <= value <= maximum:
            raise SettingsValidationError(f"{label}必須介於 {minimum} 到 {maximum}。")


settings_service = SettingsService()
