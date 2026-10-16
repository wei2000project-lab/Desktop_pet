import os
import math
import random
import time
from typing import Dict, List, Optional
from PySide6.QtCore import QObject, QTimer, Slot
from PySide6.QtGui import QImageReader
from app.utils.logger import logger
from app.core.event_bus import event_bus
from app.core.config_manager import config_manager
from app.core.paths import PET_EMOTIONS_DIR
from app.animation.blink import BlinkAnimation
from app.animation.look_around import LookAroundAnimation
from app.animation.reading import ReadingAnimation
from app.animation.emotion import EmotionPolicy, emotion_asset, load_emotion_rate, EMOTION_HOLD_MS

class Animator(QObject):
    DEFAULT_IDLE_TO_READING_SECONDS = 300
    LOOK_AROUND_CHANCE = 0.03
    BLINK_CHANCE = 0.17
    READING_ACTION_MIN_MS = 1500
    READING_ACTION_MAX_MS = 5000

    def __init__(self, *, random_value=random.random, clock=time.monotonic):
        super().__init__()
        self._clock = clock
        self._random_value = random_value
        self._stopped = False
        self._subscriptions = []
        self.emotion_rate = load_emotion_rate(config_manager)
        self._latest_request_id = 0
        self._request_open = False
        self._candidate_received = False
        self._emotion_request_id = None
        self._emotion_deadline = None
        self._emotion_policy = None
        self.idle_image_path = str(PET_EMOTIONS_DIR / "Nova_idle.png")
        
        # Load blink animation
        self.blink_anim = BlinkAnimation()
        self.look_around_anim = LookAroundAnimation()
        self.reading_anim = ReadingAnimation()

        self.current_state = "idle"
        self.active_frames: List[str] = []
        self.active_frame_index = 0
        self.idle_to_reading_seconds = self._load_idle_to_reading_seconds()
        self.last_activity_at = self._clock()

        # Frame transition timer
        self.animation_timer = QTimer(self)
        self.animation_timer.timeout.connect(self.on_animation_tick)

        # Idle check timer
        self.idle_timer = QTimer(self)
        self.idle_timer.timeout.connect(self.check_idle_state)
        self.idle_timer.start(1000) # Check every 1 second

        # Reading actions happen at random intervals after the pet enters reading mode.
        self.reading_action_timer = QTimer(self)
        self.reading_action_timer.setSingleShot(True)
        self.reading_action_timer.timeout.connect(self.play_reading_action)

        self.emotion_timer = QTimer(self)
        self.emotion_timer.setSingleShot(True)
        self.emotion_timer.timeout.connect(self.on_emotion_timeout)

        # Subscribe to animation requests
        self._subscribe("play_animation", self.play_animation)
        self._subscribe("app_started", self.on_app_started)
        self._subscribe("app_shutdown", self.shutdown)
        self._subscribe("emotion_request_started", self.on_emotion_started)
        self._subscribe("emotion_requested", self.on_emotion_requested)
        self._subscribe("emotion_request_finished", self.on_emotion_finished)
        for event_name in (
            "user_activity",
            "show_bubble",
            "hide_bubble",
            "toggle_bubble",
            "show_settings",
            "pet_moved",
            "app_open_requested",
            "app_preference_change_requested",
        ):
            self._subscribe(event_name, self.on_user_activity)
        for event_name in (
            "user_message_sent",
            "chat_response_cancel_requested",
            "ai_message_started",
            "ai_message_finished",
            "ai_message_error",
            "ai_message_cancelled",
        ):
            self._subscribe(event_name, self.record_chat_activity)
        self._subscribe("config_updated", self.on_config_updated)

    def _subscribe(self, name, callback):
        event_bus.subscribe(name, callback)
        self._subscriptions.append((name, callback))

    def record_chat_activity(self, *args, **kwargs):
        self.last_activity_at = self._clock()

    def on_emotion_started(self, request):
        if self._stopped or request.request_id <= self._latest_request_id:
            return
        self._latest_request_id = request.request_id
        self._request_open = True
        self._candidate_received = False
        self._emotion_policy = EmotionPolicy(self.emotion_rate, random_value=self._random_value)
        self.record_chat_activity()

    def on_emotion_requested(self, request):
        if (self._stopped or not self._request_open or self._candidate_received
                or request.request_id != self._latest_request_id):
            return
        self._candidate_received = True
        path = emotion_asset(request.emotion)
        # Decode before interrupting: an existing but broken PNG is not usable.
        available = path is not None and not QImageReader(str(path)).read().isNull()
        if self._emotion_policy.choose(request.emotion, asset_available=available) is None:
            return
        self._clear_emotion()
        self.animation_timer.stop()
        self.reading_action_timer.stop()
        self.active_frames = []
        self.active_frame_index = 0
        self.current_state = "emotion"
        self._emotion_request_id = request.request_id
        self.publish_frame(str(path))

    def on_emotion_finished(self, request):
        if self._stopped:
            return
        if request.request_id == self._latest_request_id:
            self._request_open = False
        if (self.current_state == "emotion" and request.request_id == self._emotion_request_id
                and self._emotion_deadline is None):
            self._emotion_deadline = self._clock() + EMOTION_HOLD_MS / 1000
            self.emotion_timer.start(EMOTION_HOLD_MS)

    def on_emotion_timeout(self):
        if self._stopped or self.current_state != "emotion" or self._emotion_deadline is None:
            return
        remaining = self._emotion_deadline - self._clock()
        if remaining > 0:
            # Qt timers can wake early, or an old timeout may already be queued.
            self.emotion_timer.start(max(1, math.ceil(remaining * 1000)))
            return
        self._clear_emotion()
        self.current_state = "idle"
        self.record_chat_activity()
        self.publish_frame(self.idle_image_path)

    def _clear_emotion(self):
        self.emotion_timer.stop()
        self._emotion_request_id = None
        self._emotion_deadline = None

    def shutdown(self):
        self._stopped = True
        self._clear_emotion()
        self.animation_timer.stop()
        self.reading_action_timer.stop()
        self.idle_timer.stop()
        for name, callback in self._subscriptions:
            event_bus.unsubscribe(name, callback)
        self._subscriptions.clear()

    def on_app_started(self):
        # Publish initial image
        self.publish_frame(self.idle_image_path)

    def check_idle_state(self):
        if self._stopped or self.current_state != "idle":
            return

        if self._clock() - self.last_activity_at >= self.idle_to_reading_seconds:
            self.enter_reading()
            return

        idle_action_roll = random.random()
        if idle_action_roll < self.LOOK_AROUND_CHANCE:
            self.play_animation("look_around")
        elif idle_action_roll < self.LOOK_AROUND_CHANCE + self.BLINK_CHANCE:
            self.play_animation("blink")

    def play_animation(self, anim_name: str):
        if self._stopped:
            return
        if anim_name in ("blink", "look_around", "reading"):
            self._clear_emotion()
            if anim_name != "reading":
                self.reading_action_timer.stop()
        if anim_name == "blink":
            self.current_state = "blinking"
            self.active_frames = self.blink_anim.frames
            self.active_frame_index = 0
            self.animation_timer.start(self.blink_anim.frame_rate_ms)
            logger.debug("Playing blink animation")
        elif anim_name == "look_around":
            self.current_state = "look_around"
            self.active_frames = self.look_around_anim.frames
            self.active_frame_index = 0
            self.animation_timer.start(self.look_around_anim.frame_rate_ms)
            logger.debug("Playing look around animation")
        elif anim_name == "reading":
            self.enter_reading()
        else:
            logger.warning(f"Unknown animation: {anim_name}")

    def on_animation_tick(self):
        if self._stopped or self.current_state not in ("blinking", "look_around", "reading_action"):
            return
        if self.active_frame_index < len(self.active_frames):
            frame_path = self.active_frames[self.active_frame_index]
            self.publish_frame(frame_path)
            self.active_frame_index += 1
        else:
            finished_state = self.current_state
            self.animation_timer.stop()
            if finished_state == "reading_action":
                self.current_state = "reading"
                self.publish_frame(self.reading_anim.idle_frame)
                self.schedule_next_reading_action()
            else:
                # Animation finished, return to idle
                self.current_state = "idle"
                self.publish_frame(self.idle_image_path)

    def enter_reading(self):
        if self._stopped or self.current_state == "reading":
            return
        self._clear_emotion()
        self.animation_timer.stop()
        self.current_state = "reading"
        self.active_frames = []
        self.active_frame_index = 0
        self.publish_frame(self.reading_anim.idle_frame)
        self.schedule_next_reading_action()
        logger.debug("Entering reading animation state")

    def play_reading_action(self):
        if self._stopped or self.current_state != "reading":
            return
        self.current_state = "reading_action"
        self.active_frames = self.reading_anim.next_sequence()
        self.active_frame_index = 0
        self.animation_timer.start(self.reading_anim.frame_rate_ms)

    def schedule_next_reading_action(self):
        if self.current_state != "reading":
            return
        interval_ms = random.randint(self.READING_ACTION_MIN_MS, self.READING_ACTION_MAX_MS)
        self.reading_action_timer.start(interval_ms)

    def on_user_activity(self, *args, **kwargs):
        if self._stopped:
            return
        self.record_chat_activity()
        if self.current_state in ("reading", "reading_action", "look_around", "emotion"):
            self._clear_emotion()
            self.reading_action_timer.stop()
            self.animation_timer.stop()
            self.current_state = "idle"
            self.active_frames = []
            self.active_frame_index = 0
            self.publish_frame(self.idle_image_path)

    def on_config_updated(self):
        self.idle_to_reading_seconds = self._load_idle_to_reading_seconds()
        self.emotion_rate = load_emotion_rate(config_manager)
        self.on_user_activity()

    def _load_idle_to_reading_seconds(self) -> int:
        value = config_manager.get_general_int("ReadingIdleSeconds", self.DEFAULT_IDLE_TO_READING_SECONDS)
        return max(10, min(3600, value))

    def publish_frame(self, path: str):
        if os.path.exists(path):
            event_bus.publish("update_pet_image", path)
        else:
            logger.error(f"Animation frame file does not exist: {path}")
