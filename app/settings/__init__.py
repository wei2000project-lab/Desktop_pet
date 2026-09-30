"""Settings data contracts and application services."""

from app.settings.model import ApiKeyEntry, SettingsSnapshot, SettingsValidationError
from app.settings.api_groups import APIGroup, APIGroupKey, APIGroupSettings, APIGroupDataError


def __getattr__(name):
    """Importing UI data contracts must not initialize configuration services."""
    from importlib import import_module

    modules = {
        "SettingsService": "service", "settings_service": "service",
        "APIGroupService": "api_group_service",
        "APIGroupResolutionError": "api_group_resolver",
        "APIRequestSnapshot": "api_group_resolver",
        "ResolvedAPIKey": "api_group_resolver",
        "resolve_api_request": "api_group_resolver",
    }
    if name not in modules:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    value = getattr(import_module(f"{__name__}.{modules[name]}"), name)
    globals()[name] = value
    return value

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
