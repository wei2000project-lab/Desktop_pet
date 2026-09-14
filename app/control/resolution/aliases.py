import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Mapping

from app.core.paths import APP_CONTROL_DATA_DIR


@dataclass(frozen=True)
class GenericAlias:
    key: str
    triggers: tuple[str, ...]
    candidates: tuple[str, ...]
    reason: str


@dataclass(frozen=True)
class AppAliasConfig:
    generic_aliases: tuple[GenericAlias, ...]
    app_aliases: Mapping[str, tuple[str, ...]]


DEFAULT_ALIAS_CONFIG = AppAliasConfig(
    generic_aliases=(
        GenericAlias(
            key="browser",
            triggers=("查詢工具", "搜尋工具", "搜索工具", "瀏覽器", "上網", "查資料", "查詢", "搜尋", "搜索"),
            candidates=("Google Chrome", "Chrome", "Microsoft Edge", "Edge", "Firefox", "Brave", "Opera"),
            reason="使用者需要查詢或上網工具",
        ),
    ),
    app_aliases={
        "chrome": ("Google Chrome", "Chrome"),
        "google chrome": ("Google Chrome", "Chrome"),
        "edge": ("Microsoft Edge", "Edge"),
        "microsoft edge": ("Microsoft Edge", "Edge"),
        "firefox": ("Firefox",),
        "brave": ("Brave",),
        "opera": ("Opera",),
        "discord": ("Discord",),
        "cmd": ("Command Prompt", "命令提示字元", "Windows Terminal", "終端機"),
        "command prompt": ("Command Prompt", "命令提示字元"),
        "命令提示字元": ("命令提示字元", "Command Prompt"),
        "命令列": ("Command Prompt", "命令提示字元", "Windows Terminal", "終端機"),
        "終端機": ("終端機", "Windows Terminal", "Command Prompt"),
    },
)


def default_app_alias_path() -> Path:
    return APP_CONTROL_DATA_DIR / "aliases.json"


def load_app_alias_config(alias_path: Path | str | None = None) -> AppAliasConfig:
    path = Path(alias_path) if alias_path is not None else default_app_alias_path()
    if not path.exists():
        return DEFAULT_ALIAS_CONFIG

    try:
        with path.open("r", encoding="utf-8") as f:
            payload = json.load(f)
    except (OSError, TypeError, ValueError, json.JSONDecodeError):
        return DEFAULT_ALIAS_CONFIG

    if not isinstance(payload, dict):
        return DEFAULT_ALIAS_CONFIG

    generic_aliases = _load_generic_aliases(payload.get("generic_aliases"))
    app_aliases = _load_app_aliases(payload.get("app_aliases"))
    return AppAliasConfig(
        generic_aliases=generic_aliases or DEFAULT_ALIAS_CONFIG.generic_aliases,
        app_aliases=app_aliases or DEFAULT_ALIAS_CONFIG.app_aliases,
    )


def _load_generic_aliases(raw_aliases) -> tuple[GenericAlias, ...]:
    if not isinstance(raw_aliases, list):
        return ()

    aliases = []
    for item in raw_aliases:
        if not isinstance(item, dict):
            continue

        triggers = _string_tuple(item.get("triggers"))
        candidates = _string_tuple(item.get("candidates"))
        key = str(item.get("key") or (triggers[0] if triggers else "")).strip().casefold()
        reason = str(item.get("reason") or "使用者輸入符合設定別名")
        if key and triggers and candidates:
            aliases.append(GenericAlias(key=key, triggers=triggers, candidates=candidates, reason=reason))

    return tuple(aliases)


def _load_app_aliases(raw_aliases) -> dict[str, tuple[str, ...]]:
    if not isinstance(raw_aliases, dict):
        return {}

    aliases = {}
    for alias, candidates in raw_aliases.items():
        alias_key = str(alias).strip().casefold()
        candidate_names = _string_tuple(candidates)
        if alias_key and candidate_names:
            aliases[alias_key] = candidate_names

    return aliases


def _string_tuple(values) -> tuple[str, ...]:
    if isinstance(values, str):
        values = [values]
    if not isinstance(values, Iterable):
        return ()

    cleaned = []
    for value in values:
        text = str(value).strip()
        if text:
            cleaned.append(text)
    return tuple(cleaned)
