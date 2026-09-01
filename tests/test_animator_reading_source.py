import pathlib
import unittest


class AnimatorReadingSourceTests(unittest.TestCase):
    def test_animator_enters_reading_after_five_idle_minutes(self):
        source = pathlib.Path("animation/animator.py").read_text(encoding="utf-8")

        self.assertIn("DEFAULT_IDLE_TO_READING_SECONDS = 300", source)
        self.assertIn("self.idle_to_reading_seconds = self._load_idle_to_reading_seconds()", source)
        self.assertIn('config_manager.get_general_int("ReadingIdleSeconds"', source)
        self.assertIn("self.last_activity_at = time.monotonic()", source)
        self.assertIn("def check_idle_state", source)
        self.assertIn("self.enter_reading()", source)
        self.assertIn("def on_config_updated", source)

    def test_animator_resets_reading_on_user_activity(self):
        source = pathlib.Path("animation/animator.py").read_text(encoding="utf-8")

        self.assertIn('"user_activity"', source)
        self.assertIn('"user_message_sent"', source)
        self.assertIn('"pet_moved"', source)
        self.assertIn("def on_user_activity", source)
        self.assertIn("self.reading_action_timer.stop()", source)

    def test_animator_schedules_random_reading_actions(self):
        source = pathlib.Path("animation/animator.py").read_text(encoding="utf-8")

        self.assertIn("READING_ACTION_MIN_MS", source)
        self.assertIn("READING_ACTION_MAX_MS", source)
        self.assertIn("random.randint", source)
        self.assertIn("self.reading_anim.next_sequence()", source)


if __name__ == "__main__":
    unittest.main()
