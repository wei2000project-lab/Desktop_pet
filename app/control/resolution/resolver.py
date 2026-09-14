from dataclasses import dataclass
from typing import Iterable, List, Mapping

from app.control.resolution.aliases import AppAliasConfig, load_app_alias_config
from app.control.discovery.index import AppEntry


class AppResolveError:
    APP_NOT_FOUND = "app_not_found"
    REQUESTED_APP_NOT_INSTALLED = "requested_app_not_installed"
    APP_CHOICE_REQUIRED = "app_choice_required"


@dataclass(frozen=True)
class AppResolveResult:
    app_name: str
    requested_name: str = ""
    reason: str = ""
    error: str = ""
    preference_key: str = ""
    choices: tuple[str, ...] = ()

    @property
    def success(self) -> bool:
        return bool(self.app_name) and not self.error


def resolve_app_from_text(
    user_text: str,
    apps: Iterable[AppEntry],
    aliases: AppAliasConfig | None = None,
    preferences: Mapping[str, str] | None = None,
) -> AppResolveResult:
    app_list = list(apps)
    alias_config = aliases or load_app_alias_config()
    preference_map = {_normalize_key(key): value for key, value in (preferences or {}).items()}
    text = user_text.strip()
    folded_text = text.casefold()

    for generic_alias in alias_config.generic_aliases:
        if any(trigger.casefold() in folded_text for trigger in generic_alias.triggers):
            installed_candidates = _resolve_all_candidates(generic_alias.candidates, app_list)
            preferred_app = _resolve_preferred_app(
                preference_map.get(_normalize_key(generic_alias.key), ""),
                installed_candidates,
            )
            if preferred_app:
                return AppResolveResult(
                    app_name=preferred_app.name,
                    reason=f"{generic_alias.reason}，使用已記住的偏好",
                    preference_key=generic_alias.key,
                )
            if len(installed_candidates) == 1:
                return AppResolveResult(
                    app_name=installed_candidates[0].name,
                    reason=generic_alias.reason,
                    preference_key=generic_alias.key,
                )
            if len(installed_candidates) > 1:
                return AppResolveResult(
                    app_name="",
                    reason=generic_alias.reason,
                    error=AppResolveError.APP_CHOICE_REQUIRED,
                    preference_key=generic_alias.key,
                    choices=tuple(app.name for app in installed_candidates),
                )

    for app in app_list:
        if _name_in_text(app.name, folded_text):
            return AppResolveResult(app_name=app.name, reason=f"使用者提到 {app.name}")

    for alias, candidates in alias_config.app_aliases.items():
        if alias in folded_text:
            resolved = _resolve_candidates(candidates, app_list)
            if resolved:
                return AppResolveResult(app_name=resolved.name, reason=f"使用者提到 {resolved.name}")
            return AppResolveResult(
                app_name="",
                requested_name=alias,
                error=AppResolveError.REQUESTED_APP_NOT_INSTALLED,
            )

    return AppResolveResult(app_name="", error=AppResolveError.APP_NOT_FOUND)


def resolve_preference_change_from_text(
    user_text: str,
    apps: Iterable[AppEntry],
    aliases: AppAliasConfig | None = None,
) -> AppResolveResult:
    app_list = list(apps)
    alias_config = aliases or load_app_alias_config()
    folded_text = user_text.strip().casefold()

    for generic_alias in alias_config.generic_aliases:
        if _generic_alias_matches_preference_text(generic_alias, folded_text):
            installed_candidates = _resolve_all_candidates(generic_alias.candidates, app_list)
            if installed_candidates:
                return AppResolveResult(
                    app_name="",
                    reason=generic_alias.reason,
                    error=AppResolveError.APP_CHOICE_REQUIRED,
                    preference_key=generic_alias.key,
                    choices=tuple(app.name for app in installed_candidates),
                )
            return AppResolveResult(
                app_name="",
                reason=generic_alias.reason,
                error=AppResolveError.REQUESTED_APP_NOT_INSTALLED,
                preference_key=generic_alias.key,
            )

    return AppResolveResult(app_name="", error=AppResolveError.APP_NOT_FOUND)


def resolve_app_name(
    app_name: str,
    apps: Iterable[AppEntry],
    aliases: AppAliasConfig | None = None,
) -> AppResolveResult:
    app_list = list(apps)
    alias_config = aliases or load_app_alias_config()
    requested = app_name.strip()
    if not requested:
        return AppResolveResult(app_name="", error=AppResolveError.APP_NOT_FOUND)

    resolved = _resolve_candidates([requested], app_list)
    if resolved:
        return AppResolveResult(app_name=resolved.name, requested_name=requested)

    alias_candidates = alias_config.app_aliases.get(requested.casefold(), ())
    resolved = _resolve_candidates(alias_candidates, app_list)
    if resolved:
        return AppResolveResult(app_name=resolved.name, requested_name=requested)

    return AppResolveResult(app_name="", requested_name=requested, error=AppResolveError.APP_NOT_FOUND)


def _resolve_all_candidates(candidates: Iterable[str], apps: List[AppEntry]) -> tuple[AppEntry, ...]:
    resolved_apps = []
    seen_names = set()
    for candidate in candidates:
        resolved = _resolve_candidates([candidate], apps)
        if resolved and resolved.name.casefold() not in seen_names:
            resolved_apps.append(resolved)
            seen_names.add(resolved.name.casefold())
    return tuple(resolved_apps)


def _resolve_preferred_app(preferred_name: str, apps: Iterable[AppEntry]) -> AppEntry | None:
    if not preferred_name.strip():
        return None
    return _resolve_candidates([preferred_name], list(apps))


def _resolve_candidates(candidates: Iterable[str], apps: List[AppEntry]) -> AppEntry | None:
    for candidate in candidates:
        folded_candidate = candidate.strip().casefold()
        for app in apps:
            if app.name.casefold() == folded_candidate:
                return app

    for candidate in candidates:
        folded_candidate = candidate.strip().casefold()
        for app in apps:
            folded_name = app.name.casefold()
            if folded_candidate and (folded_candidate in folded_name or folded_name in folded_candidate):
                return app

    return None


def _name_in_text(app_name: str, folded_text: str) -> bool:
    folded_name = app_name.casefold()
    if folded_name in folded_text:
        return True

    compact_name = folded_name.replace(" ", "")
    compact_text = folded_text.replace(" ", "")
    return compact_name in compact_text


def _generic_alias_matches_preference_text(generic_alias, folded_text: str) -> bool:
    if generic_alias.key.casefold() in folded_text:
        return True
    return any(trigger.casefold() in folded_text for trigger in generic_alias.triggers)


def _normalize_key(value: str) -> str:
    return value.strip().casefold()
