"""Settings data contracts and application services."""

from app.settings.model import ApiKeyEntry, SettingsSnapshot, SettingsValidationError
from app.settings.service import SettingsService, settings_service
from app.settings.api_groups import APIGroup, APIGroupKey, APIGroupSettings, APIGroupDataError
from app.settings.api_group_service import APIGroupService
from app.settings.api_group_resolver import (
    APIGroupResolutionError, APIRequestSnapshot, ResolvedAPIKey, resolve_api_request,
)

__all__ = [
    "APIGroup",
    "APIGroupKey",
    "APIGroupSettings",
    "APIGroupDataError",
    "APIGroupService",
    "APIGroupResolutionError",
    "APIRequestSnapshot",
    "ResolvedAPIKey",
    "resolve_api_request",
    "ApiKeyEntry",
    "SettingsService",
    "SettingsSnapshot",
    "SettingsValidationError",
    "settings_service",
]
