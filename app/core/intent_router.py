from dataclasses import dataclass
from enum import Enum


class IntentType(str, Enum):
    CHAT = "chat"
    OPEN_APP = "open_app"
    APP_PREFERENCE_CHANGE = "app_preference_change"


@dataclass(frozen=True)
class Intent:
    type: IntentType
    text: str


OPEN_APP_MARKERS = (
    "打開",
    "開啟",
    "啟動",
    "幫我開",
    "幫我打開",
    "我要上網",
    "我要寫報告",
    "我要剪影片",
)

PREFERENCE_CHANGE_MARKERS = (
    "更改",
    "修改",
    "變更",
    "重新選",
    "重選",
    "切換",
)

PREFERENCE_WORDS = (
    "偏好",
    "預設",
    "優先",
)


def route_intent(user_text: str) -> Intent:
    text = user_text.strip()
    if _looks_like_preference_change_request(text):
        return Intent(type=IntentType.APP_PREFERENCE_CHANGE, text=text)
    if _looks_like_open_app_request(text):
        return Intent(type=IntentType.OPEN_APP, text=text)
    return Intent(type=IntentType.CHAT, text=text)


def _looks_like_open_app_request(text: str) -> bool:
    if not text:
        return False
    return any(marker in text for marker in OPEN_APP_MARKERS)


def _looks_like_preference_change_request(text: str) -> bool:
    if not text:
        return False
    return any(marker in text for marker in PREFERENCE_CHANGE_MARKERS) and any(
        word in text for word in PREFERENCE_WORDS
    )
