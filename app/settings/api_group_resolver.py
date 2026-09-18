"""Resolve one group's immutable request settings without saving or sending requests."""
import math
import os
from dataclasses import dataclass, field
from typing import Mapping

from app.settings.api_groups import APIGroupDataError, APIGroupSettings, validate_api_groups
from app.settings.model import SettingsValidationError


_ERROR_MESSAGES = {
    "not_configured": "尚未建立 API 群組，請先完成設定。",
    "no_active_group": "尚未選擇目前使用的 API 群組。",
    "invalid_settings": "API 群組設定無效，請檢查設定資料。",
    "no_keys": "目前群組需要 API Key，但尚未設定金鑰。",
    "all_keys_disabled": "目前群組的 API Key 全部已暫停，請啟用至少一把。",
    "environment_unavailable": "目前群組的環境金鑰沒有值，請設定環境變數或選用其他金鑰。",
    "no_usable_key": "目前群組沒有可用的 API Key，請檢查金鑰來源與內容。",
    "invalid_temperature": "請求溫度必須介於 0.0–2.0。",
}


class APIGroupResolutionError(SettingsValidationError):
    def __init__(self, code: str):
        self.code = code
        super().__init__(_ERROR_MESSAGES[code])


@dataclass(frozen=True)
class ResolvedAPIKey:
    id: str
    name: str
    priority: int
    source: str
    key: str = field(repr=False)


@dataclass(frozen=True)
class APIRequestSnapshot:
    group_id: str
    group_name: str
    base_url: str
    model: str
    temperature: float
    verify_ssl: bool
    auth_mode: str
    candidates: tuple[ResolvedAPIKey, ...] = ()

    @property
    def selected_key(self) -> ResolvedAPIKey | None:
        """Only the first candidate is selected; this does not implement failover."""
        return self.candidates[0] if self.candidates else None

    @property
    def api_key(self) -> str | None:
        """None means explicitly unauthenticated, not a request for a fallback key."""
        return self.selected_key.key if self.selected_key is not None else None


def resolve_api_request(
    settings: APIGroupSettings | None,
    *,
    environment: Mapping[str, str] | None = None,
    temperature_override: float | None = None,
) -> APIRequestSnapshot:
    if settings is None:
        raise APIGroupResolutionError("not_configured")
    try:
        validate_api_groups(settings)
    except APIGroupDataError:
        raise APIGroupResolutionError("invalid_settings") from None
    if not settings.groups:
        raise APIGroupResolutionError("not_configured")
    if settings.active_group_id is None:
        raise APIGroupResolutionError("no_active_group")
    group = next(group for group in settings.groups if group.id == settings.active_group_id)
    temperature = group.temperature if temperature_override is None else temperature_override
    if not (type(temperature) in (int, float) and 0 <= temperature <= 2 and math.isfinite(temperature)):
        raise APIGroupResolutionError("invalid_temperature")

    candidates = []
    if group.auth_mode == "api_key":
        if not group.keys:
            raise APIGroupResolutionError("no_keys")
        enabled = [entry for entry in group.keys if entry.enabled]
        if not enabled:
            raise APIGroupResolutionError("all_keys_disabled")
        # Environment is read only for enabled references in this selected group.
        source_environment = os.environ if environment is None else environment
        for entry in sorted(enabled, key=lambda entry: entry.priority):
            value = entry.key if entry.source == "stored" else source_environment.get(entry.environment_variable, "")
            if not isinstance(value, str) or not value.strip():
                continue
            candidates.append(ResolvedAPIKey(entry.id, entry.name, entry.priority, entry.source, value.strip()))
        if not candidates:
            code = "environment_unavailable" if all(entry.source == "environment" for entry in enabled) else "no_usable_key"
            raise APIGroupResolutionError(code)

    return APIRequestSnapshot(
        group.id, group.name.strip(), group.base_url.rstrip("/"), group.model.strip(),
        float(temperature), group.verify_ssl, group.auth_mode, tuple(candidates),
    )
