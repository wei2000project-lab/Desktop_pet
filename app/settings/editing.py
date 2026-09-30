"""Normalization and feedback rules for editing settings; no widgets or persistence."""
import os
from dataclasses import dataclass, replace
from urllib.parse import urlsplit
from uuid import uuid4

from app.settings.api_groups import APIGroup, APIGroupKey, APIGroupSettings
from app.settings.api_group_resolver import APIGroupResolutionError, resolve_api_request
from app.settings.model import ApiKeyEntry, SettingsValidationError


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
            if entry.source == "stored" and not value:
                continue
            keys.append(replace(
                entry, name=entry.name.strip() or f"Key {len(keys) + 1}", key=value,
                environment_variable="OPENAI_API_KEY" if entry.source == "environment" else "",
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


@dataclass(frozen=True)
class GroupFeedback:
    status: str
    completion_path_groups: frozenset[str]
    environment_available: bool


def group_feedback(settings: APIGroupSettings) -> GroupFeedback:
    try:
        resolve_api_request(settings)
        status = ""
    except APIGroupResolutionError as error:
        status = str(error)
    return GroupFeedback(
        status,
        frozenset(group.id for group in settings.groups if has_completion_path(group.base_url)),
        bool(os.environ.get("OPENAI_API_KEY", "").strip()),
    )
