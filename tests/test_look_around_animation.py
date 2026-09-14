import pathlib
import time
import unittest
from unittest.mock import Mock, patch

from app.animation.animator import Animator
from app.animation.look_around import LookAroundAnimation
from app.core.paths import PROJECT_ROOT


class LookAroundAnimationTests(unittest.TestCase):
    def test_sequence_returns_to_front_between_directions(self):
        animation = LookAroundAnimation(str(PROJECT_ROOT))

        self.assertEqual(
            [pathlib.Path(path).name for path in animation.frames],
            [
                "Nova_looking_front.png",
                "Nova_looking_left.png",
                "Nova_looking_front.png",
                "Nova_looking_right.png",
                "Nova_looking_front.png",
            ],
        )
        self.assertEqual(animation.frame_rate_ms, 450)
        self.assertTrue(all(pathlib.Path(path).is_file() for path in animation.frames))

    def test_idle_roll_selects_look_around_blink_or_no_action(self):
        animator = Animator.__new__(Animator)
        animator.current_state = "idle"
        animator.last_activity_at = time.monotonic()
        animator.idle_to_reading_seconds = 300
        animator.play_animation = Mock()

        for roll, expected in ((0.02, "look_around"), (0.03, "blink"), (0.19, "blink")):
            animator.play_animation.reset_mock()
            with patch("app.animation.animator.random.random", return_value=roll):
                animator.check_idle_state()
            animator.play_animation.assert_called_once_with(expected)

        animator.play_animation.reset_mock()
        with patch("app.animation.animator.random.random", return_value=0.20):
            animator.check_idle_state()
        animator.play_animation.assert_not_called()

    def test_play_animation_starts_look_around_frames(self):
        animator = Animator.__new__(Animator)
        animator.look_around_anim = LookAroundAnimation(str(PROJECT_ROOT))
        animator.animation_timer = Mock()

        animator.play_animation("look_around")

        self.assertEqual(animator.current_state, "look_around")
        self.assertEqual(animator.active_frames, animator.look_around_anim.frames)
        self.assertEqual(animator.active_frame_index, 0)
        animator.animation_timer.start.assert_called_once_with(450)

    def test_user_activity_interrupts_look_around(self):
        animator = Animator.__new__(Animator)
        animator.current_state = "look_around"
        animator.last_activity_at = 0
        animator.active_frames = ["frame"]
        animator.active_frame_index = 1
        animator.idle_image_path = "idle.png"
        animator.reading_action_timer = Mock()
        animator.animation_timer = Mock()
        animator.publish_frame = Mock()

        animator.on_user_activity()

        self.assertEqual(animator.current_state, "idle")
        self.assertEqual(animator.active_frames, [])
        self.assertEqual(animator.active_frame_index, 0)
        animator.reading_action_timer.stop.assert_called_once_with()
        animator.animation_timer.stop.assert_called_once_with()
        animator.publish_frame.assert_called_once_with("idle.png")


if __name__ == "__main__":
    unittest.main()
