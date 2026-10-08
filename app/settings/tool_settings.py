"""Version-2 tool settings keep API credentials in .env only."""
import json
from typing import Any


TOOL_SCHEMA_VERSION = 2
TOOL_KEY_ENV = "NOVA_TOOL_API_KEY"


def prepare_tool_settings_v2(
    payload: dict[str, Any], *, replacement: str = "", clear: bool = False,
) -> tuple[str, dict[str, str | None], frozenset[str]]:
    """Convert one tool document; blank replacement preserves its current key."""
    if not isinstance(payload, dict):
        raise ValueError("工具設定格式無效。")
    if payload.get("schema_version") not in (None, TOOL_SCHEMA_VERSION):
        raise ValueError("不支援的工具設定版本。")
    result = dict(payload)
    raw_key = result.pop("tavily_api_key", None)
    name = result.get("tavily_api_key_env")
    if name is not None and name != TOOL_KEY_ENV:
        raise ValueError("工具環境變數名稱格式無效。")
    owned = frozenset((name,)) if payload.get("schema_version") == TOOL_SCHEMA_VERSION and name else frozenset()
    updates: dict[str, str | None] = {}
    if raw_key is not None:
        if not isinstance(raw_key, str):
            raise ValueError("工具金鑰格式無效。")
        if raw_key.strip():
            name = name or TOOL_KEY_ENV
            updates[name] = raw_key.strip()
    if replacement:
        if not isinstance(replacement, str) or "\n" in replacement or "\r" in replacement:
            raise ValueError("工具金鑰格式無效。")
        if replacement.strip():
            name = name or TOOL_KEY_ENV
            updates[name] = replacement.strip()
    if clear:
        if name in owned:
            updates[name] = None
        else:
            updates.pop(name, None)
        name = None
    if name:
        result["tavily_api_key_env"] = name
    else:
        result.pop("tavily_api_key_env", None)
    result["schema_version"] = TOOL_SCHEMA_VERSION
    return json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n", updates, owned
