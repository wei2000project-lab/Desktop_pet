import os
import random
import time
from typing import Dict, List, Optional
from PySide6.QtCore import QObject, QTimer, Slot
from app.utils.logger import logger
from app.core.event_bus import event_bus
from app.core.config_manager import config_manager
from app.animation.blink import BlinkAnimation
from app.animation.reading import ReadingAnimation

class Animator(QObject):
    DEFAULT_IDLE_TO_READING_SECONDS = 300
    READING_ACTION_MIN_MS = 1500
    READING_ACTION_MAX_MS = 5000

    def __init__(self, base_dir: str):
        super().__init__()
        self.base_dir = base_dir
        self.idle_image_path = os.path.join(base_dir, "assets", "images", "Nova.png")
        
        # Load blink animation
        self.blink_anim = BlinkAnimation(base_dir)
        self.reading_anim = ReadingAnimation(base_dir)

        self.current_state = "idle"
        self.active_frames: List[str] = []
        self.active_frame_index = 0
        self.idle_to_reading_seconds = self._load_idle_to_reading_seconds()
        self.last_activity_at = time.monotonic()

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

        # Subscribe to animation requests
        event_bus.subscribe("play_animation", self.play_animation)
        event_bus.subscribe("app_started", self.on_app_started)
        for event_name in (
            "user_activity",
            "show_bubble",
            "hide_bubble",
            "show_settings",
            "pet_moved",
            "user_message_sent",
            "chat_response_cancel_requested",
            "app_open_requested",
            "app_preference_change_requested",
            "ai_message_started",
            "ai_message_finished",
            "ai_message_error",
            "ai_message_cancelled",
        ):
            event_bus.subscribe(event_name, self.on_user_activity)
        event_bus.subscribe("config_updated", self.on_config_updated)

    def on_app_started(self):
        # Publish initial image
        self.publish_frame(self.idle_image_path)

    def check_idle_state(self):
        if self.current_state != "idle":
            return

        if time.monotonic() - self.last_activity_at >= self.idle_to_reading_seconds:
            self.enter_reading()
            return

        if random.random() < 0.2: # 20% chance
            self.play_animation("blink")

    def play_animation(self, anim_name: str):
        if anim_name == "blink":
            self.current_state = "blinking"
            self.active_frames = self.blink_anim.frames
            self.active_frame_index = 0
            self.animation_timer.start(self.blink_anim.frame_rate_ms)
            logger.debug("Playing blink animation")
        elif anim_name == "reading":
            self.enter_reading()
        else:
            logger.warning(f"Unknown animation: {anim_name}")

    def on_animation_tick(self):
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
        if self.current_state == "reading":
            return
        self.animation_timer.stop()
        self.current_state = "reading"
        self.active_frames = []
        self.active_frame_index = 0
        self.publish_frame(self.reading_anim.idle_frame)
        self.schedule_next_reading_action()
        logger.debug("Entering reading animation state")

    def play_reading_action(self):
        if self.current_state != "reading":
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
        self.last_activity_at = time.monotonic()
        if self.current_state in ("reading", "reading_action"):
            self.reading_action_timer.stop()
            self.animation_timer.stop()
            self.current_state = "idle"
            self.active_frames = []
            self.active_frame_index = 0
            self.publish_frame(self.idle_image_path)

    def on_config_updated(self):
        self.idle_to_reading_seconds = self._load_idle_to_reading_seconds()
        self.on_user_activity()

    def _load_idle_to_reading_seconds(self) -> int:
        value = config_manager.get_general_int("ReadingIdleSeconds", self.DEFAULT_IDLE_TO_READING_SECONDS)
        return max(10, min(3600, value))

    def publish_frame(self, path: str):
        if os.path.exists(path):
            event_bus.publish("update_pet_image", path)
        else:
            logger.error(f"Animation frame file does not exist: {path}")
