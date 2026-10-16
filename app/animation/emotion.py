"""Emotion assets and one decision per reply, without Qt or service initialization."""
import math
from pathlib import Path
import random

from app.contracts.emotion import Emotion
from app.core.paths import PET_EMOTIONS_DIR


DEFAULT_EMOTION_RATE = 0.3
EMOTION_HOLD_MS = 3000
_ASSET_NAMES = {
    Emotion.HAPPY: "Nova_happy.png",
    Emotion.SURPRISED: "Nova_surprised.png",
    Emotion.SQUINT: "Nova_squint.png",
}


def normalize_emotion_rate(value):
    if isinstance(value, bool):
        return DEFAULT_EMOTION_RATE
    try:
        rate = float(value)
    except (TypeError, ValueError, OverflowError):
        return DEFAULT_EMOTION_RATE
    return rate if math.isfinite(rate) and 0 <= rate <= 1 else DEFAULT_EMOTION_RATE


def load_emotion_rate(store):
    """Use the existing layered configuration without importing its singleton."""
    return normalize_emotion_rate(store.get_general("EmotionRate", DEFAULT_EMOTION_RATE))


def emotion_asset(emotion, emotions_dir=PET_EMOTIONS_DIR):
    """Only known non-idle names can resolve to files; never accept model paths."""
    try:
        choice = Emotion(emotion)
    except (TypeError, ValueError):
        return None
    filename = _ASSET_NAMES.get(choice)
    if filename is None:
        return None
    path = Path(emotions_dir) / filename
    return path if path.is_file() else None


class EmotionPolicy:
    """Create one per request. Later calls cannot re-roll or change its decision.

    The caller checks the asset before choosing, then performs any animation work.
    This class itself never changes frames, timers, or application state.
    """
    def __init__(self, rate=DEFAULT_EMOTION_RATE, *, random_value=random.random):
        self.rate = normalize_emotion_rate(rate)
        self.random_value = random_value
        self.decided = False
        self.selected = None

    def choose(self, emotion, *, asset_available=True):
        if self.decided:
            return self.selected
        self.decided = True
        try:
            choice = Emotion(emotion)
        except (TypeError, ValueError):
            return None
        if choice is Emotion.NONE or not asset_available or self.rate == 0:
            return None
        if self.rate == 1 or self.random_value() < self.rate:
            self.selected = choice
        return self.selected
