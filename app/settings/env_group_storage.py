"""Prepare version-2 group data and local .env updates without writing files."""
from dataclasses import replace

from app.settings.api_groups import (
    APIGroupDataError, APIGroupSettings, ENV_SCHEMA_VERSION,
    managed_key_name, validate_api_groups,
)


def prepare_env_groups(
    draft: APIGroupSettings, previous: APIGroupSettings | None,
) -> tuple[APIGroupSettings, dict[str, str | None], frozenset[str]]:
    """Return secret-free groups, changed variables, and previously owned names.

    A blank draft value keeps its existing .env value. Removing a stored key
    produces an explicit deletion only for a variable owned by the old v2 file.
    """
    validate_api_groups(draft)
    if previous is not None:
        validate_api_groups(previous)
    owned = frozenset(
        key.environment_variable
        for group in (previous.groups if previous and previous.schema_version == ENV_SCHEMA_VERSION else ())
        for key in group.keys if key.source == "stored"
    )
    used = set()
    updates: dict[str, str | None] = {}
    groups = []
    for group in draft.groups:
        keys = []
        for key in group.keys:
            if key.source != "stored":
                keys.append(replace(key, key=""))
                continue
            name = key.environment_variable or managed_key_name(key.id)
            if name in used:
                raise APIGroupDataError("儲存 Key 的環境變數引用重複。")
            if key.environment_variable and name not in owned and name != managed_key_name(key.id):
                raise APIGroupDataError("不能修改不屬於此設定的環境變數。")
            used.add(name)
            if key.key.strip():
                updates[name] = key.key.strip()
            elif name not in owned:
                raise APIGroupDataError("新金鑰沒有內容。")
            keys.append(replace(key, key="", environment_variable=name))
        groups.append(replace(group, keys=tuple(keys)))
    for name in owned - used:
        if not any(key.environment_variable == name for group in groups for key in group.keys):
            updates[name] = None
    prepared = replace(draft, groups=tuple(groups), schema_version=ENV_SCHEMA_VERSION)
    validate_api_groups(prepared)
    return prepared, updates, owned
