"""Build view data from application state; no Qt or widget access."""
import os
from dataclasses import fields

from app.contracts.settings import (
    APIGroupDisplay, APIKeyDisplay, APIGroupsDisplay, LegacyKeyInput, SettingsDisplay,
)
from app.settings.api_groups import ENV_SCHEMA_VERSION


def settings_display(snapshot):
    values = {item.name: getattr(snapshot, item.name) for item in fields(SettingsDisplay)}
    values["api_keys"] = tuple(LegacyKeyInput(entry.name, entry.key) for entry in snapshot.api_keys)
    return SettingsDisplay(**values)


def key_display(entry, schema_version, environment=None):
    environment = os.environ if environment is None else environment
    saved_reference = (schema_version == ENV_SCHEMA_VERSION and entry.source == "stored"
                       and bool(entry.environment_variable))
    value = entry.key
    if saved_reference and not value:
        value = environment.get(entry.environment_variable, "")
    if entry.source == "environment":
        value = ""
    return APIKeyDisplay(
        entry.id, entry.name, value, entry.priority, entry.enabled, entry.source,
        placeholder="已保存引用；留空表示保留原金鑰" if saved_reference else "",
    )


def group_display(group, schema_version, environment=None):
    return APIGroupDisplay(
        group.id, group.name, group.base_url, group.model, group.temperature,
        group.verify_ssl, group.auth_mode,
        tuple(key_display(key, schema_version, environment) for key in group.keys),
    )


def groups_display(settings, enabled=True, error=None, environment=None):
    return APIGroupsDisplay(
        tuple(group_display(group, settings.schema_version, environment) for group in settings.groups),
        settings.active_group_id, enabled, error,
    )
