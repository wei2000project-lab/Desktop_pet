import os
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QThread
from app.animation.animator import Animator
from app.animation.emotion import EMOTION_HOLD_MS
from app.contracts.emotion import Emotion, EmotionStarted, EmotionRequest, EmotionFinished
from tests.emotion_helpers import EmotionTestBus


class AnimatorEmotionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.bus = EmotionTestBus()
        self.now = 100.0
        self.roll = Mock(return_value=0.1)
        store = Mock()
        store.get_general.return_value = "0.3"
        store.get_general_int.return_value = 300
        for target, value in (("event_bus", self.bus), ("config_manager", store)):
            patcher = patch("app.animation.animator." + target, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.animator = Animator(random_value=self.roll, clock=lambda: self.now)

    def tearDown(self):
        self.animator.shutdown()
        self.animator.deleteLater()
        self.app.processEvents()

    def start(self, request_id=1, emotion=Emotion.HAPPY):
        self.bus.publish("emotion_request_started", EmotionStarted(request_id))
        self.bus.publish("emotion_requested", EmotionRequest(request_id, emotion))

    def frames(self):
        return self.bus.values("update_pet_image")

    def test_adoption_immediately_interrupts_each_animation(self):
        for index, action in enumerate(("blink", "look_around", "reading", "reading_action"), 1):
            with self.subTest(action=action):
                self.animator.play_animation("reading" if action == "reading_action" else action)
                if action == "reading_action":
                    self.animator.play_reading_action()
                self.start(index, Emotion.SQUINT)
                self.assertEqual(self.animator.current_state, "emotion")
                self.assertTrue(self.frames()[-1].endswith("Nova_squint.png"))
                self.assertFalse(self.animator.animation_timer.isActive())
                self.assertFalse(self.animator.reading_action_timer.isActive())
                count = len(self.frames())
                self.animator.on_animation_tick()
                self.animator.play_reading_action()
                self.animator.check_idle_state()
                self.assertEqual(len(self.frames()), count)

    def test_runtime_ini_rate_one_reaches_animator_and_does_not_roll(self):
        from app.core.config_manager import ConfigManager, read_layered_ini
        from app.core.paths import PROJECT_ROOT
        with tempfile.TemporaryDirectory() as directory:
            runtime = Path(directory) / "app.ini"
            runtime.write_text("[General]\nEmotionRate = 1\n", encoding="utf-8")
            store = object.__new__(ConfigManager)
            store.general_config = read_layered_ini(PROJECT_ROOT / "data/config/app.defaults.ini", runtime)
            self.roll.side_effect = AssertionError("rate=1 must not sample")
            with patch("app.animation.animator.config_manager", store):
                self.animator.on_config_updated()
            with self.assertNoLogs("nova", level="DEBUG"):
                self.start(emotion=Emotion.HAPPY)
            self.assertEqual(self.animator.emotion_rate, 1)
            self.assertTrue(self.frames()[-1].endswith("Nova_happy.png"))
            self.assertEqual(self.animator.current_state, "emotion")
            self.roll.assert_not_called()

    def test_skipped_emotions_do_not_write_diagnostic_logs(self):
        self.roll.return_value = 0.99
        with self.assertNoLogs("nova", level="DEBUG"):
            self.start(1, Emotion.HAPPY)
            self.start(2, Emotion.NONE)
            with patch("app.animation.animator.emotion_asset", return_value=None):
                self.start(3, Emotion.SQUINT)

    def test_none_and_missed_roll_leave_current_animation_running(self):
        for request_id, emotion in ((1, Emotion.NONE), (2, Emotion.HAPPY)):
            self.roll.return_value = 0.9
            self.animator.play_animation("look_around")
            index = self.animator.active_frame_index
            count = len(self.frames())
            self.start(request_id, emotion)
            self.bus.publish("emotion_request_finished", EmotionFinished(request_id))
            for event in ("user_message_sent", "ai_message_started", "ai_message_finished",
                          "ai_message_error", "ai_message_cancelled", "chat_response_cancel_requested"):
                self.bus.publish(event)
            self.assertEqual(self.animator.current_state, "look_around")
            self.assertTrue(self.animator.animation_timer.isActive())
            self.assertEqual(len(self.frames()), count)
            self.animator.on_animation_tick()
            self.assertEqual(self.animator.active_frame_index, index + 1)
        self.roll.assert_called_once()

    def test_reading_survives_chat_and_keeps_its_schedule(self):
        self.animator.enter_reading()
        self.start(emotion=Emotion.NONE)
        self.bus.publish("user_message_sent", "hello")
        self.bus.publish("ai_message_finished", "hello")
        self.assertEqual(self.animator.current_state, "reading")
        self.assertTrue(self.animator.reading_action_timer.isActive())
        self.animator.play_animation("reading")
        self.assertTrue(self.animator.reading_action_timer.isActive())

    def test_hold_starts_at_finish_and_duplicate_finish_does_not_extend(self):
        self.start()
        self.now += 30
        self.animator.on_emotion_timeout()
        self.assertEqual(self.animator.current_state, "emotion")
        self.assertFalse(self.animator.emotion_timer.isActive())
        self.bus.publish("emotion_request_finished", EmotionFinished(1))
        self.assertEqual(self.animator.emotion_timer.interval(), 1500)
        deadline = self.now + EMOTION_HOLD_MS / 1000
        self.now = deadline - 0.1
        self.bus.publish("emotion_request_finished", EmotionFinished(1))
        self.animator.on_emotion_timeout()
        self.assertEqual(self.animator.current_state, "emotion")
        self.now = deadline
        self.animator.on_emotion_timeout()
        self.assertEqual(self.animator.current_state, "idle")
        self.assertTrue(self.frames()[-1].endswith("Nova_idle.png"))

    def test_new_emotion_ignores_old_finish_and_queued_timeout(self):
        self.start()
        self.bus.publish("emotion_request_finished", EmotionFinished(1))
        self.now += 0.5
        self.start(2, Emotion.SURPRISED)
        self.bus.publish("emotion_request_finished", EmotionFinished(1))
        self.now += 1
        self.animator.on_emotion_timeout()
        self.assertEqual(self.animator.current_state, "emotion")
        self.assertTrue(self.frames()[-1].endswith("Nova_surprised.png"))
        self.bus.publish("emotion_request_finished", EmotionFinished(2))
        self.animator.on_emotion_timeout()
        self.assertEqual(self.animator.current_state, "emotion")
        self.now += EMOTION_HOLD_MS / 1000
        self.animator.on_emotion_timeout()
        self.assertEqual(self.animator.current_state, "idle")

    def test_none_in_new_request_does_not_reset_previous_emotion_deadline(self):
        self.start()
        self.bus.publish("emotion_request_finished", EmotionFinished(1))
        self.now += 0.5
        self.start(2, Emotion.NONE)
        self.bus.publish("emotion_request_finished", EmotionFinished(2))
        self.now += 1
        self.animator.on_emotion_timeout()
        self.assertEqual(self.animator.current_state, "idle")

    def test_duplicates_and_late_candidate_after_end_do_not_reroll(self):
        self.start()
        self.bus.publish("emotion_requested", EmotionRequest(1, Emotion.SQUINT))
        self.roll.assert_called_once()
        self.bus.publish("emotion_request_started", EmotionStarted(2))
        self.bus.publish("emotion_request_finished", EmotionFinished(2))
        self.bus.publish("emotion_requested", EmotionRequest(2, Emotion.SQUINT))
        self.bus.publish("emotion_requested", EmotionRequest(1, Emotion.SQUINT))
        self.roll.assert_called_once()
        self.assertTrue(self.frames()[-1].endswith("Nova_happy.png"))

    def test_missing_and_corrupt_images_do_not_interrupt_or_roll(self):
        with tempfile.TemporaryDirectory() as directory:
            corrupt = Path(directory) / "broken.png"
            corrupt.write_text("not an image")
            for request_id, path in ((1, None), (2, corrupt)):
                self.animator.play_animation("blink")
                with patch("app.animation.animator.emotion_asset", return_value=path):
                    self.start(request_id)
                self.assertEqual(self.animator.current_state, "blinking")
                self.assertTrue(self.animator.animation_timer.isActive())
        self.roll.assert_not_called()

    def test_explicit_animation_and_interaction_revoke_expiry(self):
        self.start()
        self.bus.publish("emotion_request_finished", EmotionFinished(1))
        self.animator.play_animation("reading")
        self.now += EMOTION_HOLD_MS / 1000
        self.animator.on_emotion_timeout()
        self.assertEqual(self.animator.current_state, "reading")
        self.start(2)
        self.bus.publish("pet_moved", 10, 20)
        self.assertEqual(self.animator.current_state, "idle")
        self.assertFalse(self.animator.emotion_timer.isActive())

    def test_shutdown_stops_timers_and_unsubscribes(self):
        self.start()
        self.bus.publish("app_shutdown")
        count = len(self.frames())
        self.now += 5
        self.animator.on_emotion_timeout()
        self.animator.on_animation_tick()
        self.assertEqual(len(self.frames()), count)
        self.assertTrue(all(not callbacks for callbacks in self.bus.listeners.values()))
        for timer in (self.animator.animation_timer, self.animator.reading_action_timer,
                      self.animator.idle_timer, self.animator.emotion_timer):
            self.assertFalse(timer.isActive())

    def test_real_event_bus_dispatches_worker_emotion_on_qt_thread(self):
        from app.core.event_bus import event_bus
        frames = []
        def record(path):
            frames.append((path, QThread.currentThread()))
        # Temporarily use the real Qt event dispatcher; the ordinary fixture
        # animator stays subscribed only to its own test bus.
        with patch("app.animation.animator.event_bus", event_bus):
            animator = Animator(random_value=lambda: 0.0, clock=lambda: self.now)
            event_bus.subscribe("update_pet_image", record)
            try:
                event_bus.publish("emotion_request_started", EmotionStarted(10001))
                def deliver():
                    event_bus.publish("emotion_requested", EmotionRequest(10001, Emotion.HAPPY))
                    event_bus.publish("emotion_request_finished", EmotionFinished(10001))
                worker = threading.Thread(target=deliver)
                worker.start()
                worker.join(timeout=5)
                self.assertFalse(worker.is_alive())
                self.assertEqual(frames, [])
                self.app.processEvents()
                self.assertEqual(animator.current_state, "emotion")
                self.assertTrue(animator.emotion_timer.isActive())
                self.assertEqual(len(frames), 1)
                self.assertTrue(frames[0][0].endswith("Nova_happy.png"))
                self.assertEqual(frames[0][1], self.app.thread())
            finally:
                animator.shutdown()
                event_bus.unsubscribe("update_pet_image", record)
                animator.deleteLater()
                self.app.processEvents()
