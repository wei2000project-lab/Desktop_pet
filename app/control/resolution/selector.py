import json
import re
from dataclasses import dataclass
from typing import Callable, Iterable, List

from app.control.resolution.aliases import AppAliasConfig
from app.control.resolution.confidence import LOW_CONFIDENCE_THRESHOLD
from app.control.discovery.index import AppEntry
from app.control.preferences import AppPreferenceStore
from app.control.resolution.resolver import AppResolveError, resolve_app_from_text, resolve_app_name


CompletionFn = Callable[[List[dict]], str]


@dataclass(frozen=True)
class AppSelection:
    action: str
    app_name: str
    confidence: float
    reason: str
    error: str = ""
    preference_key: str = ""
    choices: tuple[str, ...] = ()

    @property
    def success(self) -> bool:
        return self.action == "open_app" and bool(self.app_name) and not self.error


def parse_app_selection(raw_text: str) -> AppSelection:
    try:
        payload = json.loads(_extract_json_text(raw_text))
    except (TypeError, ValueError, json.JSONDecodeError):
        return AppSelection(action="none", app_name="", confidence=0.0, reason="", error="invalid_json")

    action = str(payload.get("action") or "none")
    app_name = str(payload.get("app_name") or "")
    reason = str(payload.get("reason") or "")

    try:
        confidence = float(payload.get("confidence", 0.0))
    except (TypeError, ValueError):
        confidence = 0.0

    return AppSelection(
        action=action,
        app_name=app_name,
        confidence=confidence,
        reason=reason,
    )


class AppSelector:
    def __init__(
        self,
        complete: CompletionFn,
        aliases: AppAliasConfig | None = None,
        preference_store: AppPreferenceStore | None = None,
    ):
        self.complete = complete
        self.aliases = aliases
        self.preference_store = preference_store

    def select_app(self, user_text: str, apps: Iterable[AppEntry]) -> AppSelection:
        app_list = list(apps)
        app_names = [app.name for app in app_list]
        if not app_names:
            return AppSelection(action="none", app_name="", confidence=0.0, reason="", error="empty_app_index")

        local_selection = resolve_app_from_text(
            user_text,
            app_list,
            aliases=self.aliases,
            preferences=self._load_preferences(),
        )
        if local_selection.success:
            return AppSelection(
                action="open_app",
                app_name=local_selection.app_name,
                confidence=1.0,
                reason=local_selection.reason,
                preference_key=local_selection.preference_key,
            )
        if local_selection.error == AppResolveError.APP_CHOICE_REQUIRED:
            return AppSelection(
                action="none",
                app_name="",
                confidence=0.0,
                reason=local_selection.reason,
                error="app_choice_required",
                preference_key=local_selection.preference_key,
                choices=local_selection.choices,
            )
        if local_selection.error == AppResolveError.REQUESTED_APP_NOT_INSTALLED:
            return AppSelection(
                action="none",
                app_name=local_selection.requested_name,
                confidence=0.0,
                reason="使用者指定的應用程式不在本機清單中",
                error="requested_app_not_installed",
            )

        raw_response = self.complete(_build_selection_messages(user_text, app_names))
        selection = parse_app_selection(raw_response)
        if selection.error:
            return selection

        if selection.action != "open_app":
            return AppSelection(
                action=selection.action,
                app_name=selection.app_name,
                confidence=selection.confidence,
                reason=selection.reason,
                error="unsupported_action",
            )

        resolved_selection = resolve_app_name(selection.app_name, app_list, aliases=self.aliases)
        if not resolved_selection.success:
            return AppSelection(
                action=selection.action,
                app_name=selection.app_name,
                confidence=selection.confidence,
                reason=selection.reason,
                error="app_not_in_index",
            )

        if selection.confidence < LOW_CONFIDENCE_THRESHOLD:
            return AppSelection(
                action="none",
                app_name=resolved_selection.app_name,
                confidence=selection.confidence,
                reason=selection.reason,
                error="low_confidence",
            )

        return AppSelection(
            action=selection.action,
            app_name=resolved_selection.app_name,
            confidence=selection.confidence,
            reason=selection.reason,
        )

    def _load_preferences(self) -> dict[str, str]:
        if not self.preference_store:
            return {}
        return self.preference_store.load_preferences()


def _extract_json_text(raw_text: str) -> str:
    text = raw_text.strip()
    fenced = re.search(r"```(?:json)?\s*(.*?)\s*```", text, flags=re.DOTALL | re.IGNORECASE)
    if fenced:
        return fenced.group(1).strip()
    return text


def _build_selection_messages(user_text: str, app_names: List[str]) -> List[dict]:
    app_list = "\n".join(f"- {name}" for name in app_names)
    return [
        {
            "role": "system",
            "content": (
                "你是 Windows 桌寵的應用程式選擇器。"
                "你只能從提供的 App 名稱清單中選一個最適合使用者需求的 App。"
                "不可回傳路徑、不可回傳命令、不可回傳清單外名稱。"
                "只回傳 JSON，不要加其他文字。"
                '格式：{"action":"open_app","app_name":"App 名稱","confidence":0.0,"reason":"原因"}'
            ),
        },
        {
            "role": "user",
            "content": f"使用者輸入：{user_text}\n\n可選 App 名稱清單：\n{app_list}",
        },
    ]
