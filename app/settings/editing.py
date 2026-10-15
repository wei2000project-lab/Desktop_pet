"""Normalization and feedback rules for editing settings; no widgets or persistence."""
import os
from dataclasses import replace
from urllib.parse import urlsplit
from uuid import uuid4

from app.settings.api_groups import APIGroup, APIGroupKey, APIGroupSettings, ENV_SCHEMA_VERSION
from app.settings.api_group_resolver import APIGroupResolutionError, resolve_api_request
from app.settings.model import ApiKeyEntry, SettingsValidationError
from app.contracts.settings import GroupFeedback


def groups_from_input(form, baseline):
    """Interpret raw edits against the load-time baseline, not the last keystroke.

    The baseline retains empty new rows and original sources. Normalizing a draft
    must not erase information needed when the user switches a source back.
    """
    originals = {group.id: group for group in baseline.groups}
    groups = []
    for row in form.groups:
        original = originals.get(row.id)
        old_keys = {key.id: key for key in original.keys} if original else {}
        keys = []
        for value in row.keys:
            old = old_keys.get(value.id, APIGroupKey(value.id, ""))
            key = value.key
            if (baseline.schema_version == ENV_SCHEMA_VERSION and old.source == "stored"
                    and old.environment_variable and not old.key and not value.key_edited):
                key = ""
            variable = ("OPENAI_API_KEY" if value.source == "environment" else
                        old.environment_variable if old.source == "stored" else "")
            keys.append(APIGroupKey(value.id, value.name, key, value.priority,
                                    value.enabled, value.source, variable))
        temperature = (original.temperature if original and not row.temperature_edited
                       else row.temperature)
        groups.append(APIGroup(row.id, row.name, row.base_url, row.model, temperature,
                               row.verify_ssl, row.auth_mode, tuple(keys)))
    return APIGroupSettings(tuple(groups), form.active_group_id, baseline.schema_version)


def new_api_group():
    return APIGroup(str(uuid4()), "新 API 群組", "https://api.openai.com/v1", "gpt-4o-mini")


def new_api_key():
    return APIGroupKey(str(uuid4()), "", "")


def normalize_key_entries(entries):
    result = []
    for entry in entries:
        if entry.key.strip():
            result.append(ApiKeyEntry(entry.name.strip() or f"Key {len(result) + 1}", entry.key.strip()))
    return tuple(result)


def normalize_group_input(settings: APIGroupSettings) -> APIGroupSettings:
    groups = []
    for group in settings.groups:
        keys = []
        for entry in group.keys:
            value = entry.key.strip() if entry.source == "stored" else ""
            if entry.source == "stored" and not value and not (
                settings.schema_version == ENV_SCHEMA_VERSION and entry.environment_variable
            ):
                continue
            keys.append(replace(
                entry, name=entry.name.strip() or f"Key {len(keys) + 1}", key=value,
                environment_variable=(entry.environment_variable or "OPENAI_API_KEY") if entry.source == "environment"
                else (entry.environment_variable if settings.schema_version == ENV_SCHEMA_VERSION else ""),
            ))
        groups.append(replace(group, name=group.name.strip(), base_url=group.base_url.strip(),
                              model=group.model.strip(), keys=tuple(keys)))
    return replace(settings, groups=tuple(groups))


def has_completion_path(url: str) -> bool:
    try:
        return urlsplit(url.strip()).path.rstrip("/").lower().endswith("/chat/completions")
    except ValueError:
        return False  # Structural URL validation supplies the error on apply.


def validate_group_draft(settings: APIGroupSettings) -> None:
    if any(has_completion_path(group.base_url) for group in settings.groups):
        raise SettingsValidationError("Base URL 請填 API 根路徑，不要包含 /chat/completions。")


def group_feedback(settings: APIGroupSettings, form=None, baseline=None) -> GroupFeedback:
    try:
        resolve_api_request(settings)
        status = ""
    except APIGroupResolutionError as error:
        status = str(error)
    available = bool(os.environ.get("OPENAI_API_KEY", "").strip())
    originals = {(group.id, key.id): key for group in (baseline or settings).groups for key in group.keys}
    statuses = {}
    for group in (form or settings).groups:
        for key in group.keys:
            original = originals.get((group.id, key.id))
            if key.source == "environment":
                message = "環境來源已設定（不顯示或保存內容）" if available else "環境來源尚無值"
            elif (settings.schema_version == ENV_SCHEMA_VERSION and original
                  and original.environment_variable and not key.key
                  and (form is not None or not os.environ.get(original.environment_variable, ""))):
                message = "已保存引用；留空保留，刪除 Key 可清除"
            else:
                message = "啟用" if key.enabled else "X：已暫停，原順位保留"
            statuses[(group.id, key.id)] = message
    return GroupFeedback(
        status,
        frozenset(group.id for group in settings.groups if has_completion_path(group.base_url)),
        available, statuses,
    )
