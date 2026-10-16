"""Data-only emotion choices and request lifecycle events."""
from dataclasses import dataclass
from enum import Enum


class Emotion(str, Enum):
    HAPPY = "happy"
    SURPRISED = "surprised"
    SQUINT = "squint"
    NONE = "none"


@dataclass(frozen=True)
class EmotionStarted:
    request_id: int


@dataclass(frozen=True)
class EmotionRequest:
    request_id: int
    emotion: Emotion


@dataclass(frozen=True)
class EmotionFinished:
    """The request ended, whether completed, cancelled, or failed."""
    request_id: int
